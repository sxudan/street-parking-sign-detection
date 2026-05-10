"""
detect_signs.py
---------------
Free, local OCR pipeline for Australian street-parking signs.

Pipeline:
  1. Preprocess image (grayscale + CLAHE + adaptive threshold) so
     Tesseract has the cleanest possible input.
  2. Run Tesseract via image_to_data so we get per-word confidence
     scores AND bounding boxes — not just a flat string.
  3. Throw away any word with conf < 40 (Tesseract noise / hallucinations).
  4. Score the surviving text against a tiered keyword dictionary using
     WORD-BOUNDARY matching (so "MON" inside "MONITORING" doesn't count).
  5. Return both the score and the per-word bounding boxes so the HTML
     contact sheet can draw rectangles around what Tesseract actually
     read.

Scoring:
  STRONG keywords (e.g. "NO STOPPING", "LOADING ZONE", "PERMIT ZONE")
  are worth 3 points each — any one of them alone passes the default
  flag threshold of 3.0.

  P-codes (1P, 2P, 4P, 1/4P, 1/2P) and time ranges (e.g. "8:30-18:30")
  are also worth 3 points and 2 points respectively.

  WEAK keywords (MON, TUE, AM, PM, etc.) are worth 0.5 each, capped at
  4. So a noisy frame that hallucinates only "PM" (1 weak = 0.5
  points) does NOT pass the threshold. Only the combination of
  multiple distinct weaks, or a strong keyword, will.

Dependencies: opencv-python-headless, pytesseract, and the tesseract
binary installed on the system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

try:
    import pytesseract
    from pytesseract import Output
    _TESSERACT_OK = True
except ImportError:
    _TESSERACT_OK = False


# ---------------------------------------------------------------------------
# Keyword tiers
# ---------------------------------------------------------------------------

# A single hit on any STRONG keyword is enough to cross the flag threshold.
STRONG_KEYWORDS = [
    "NO STOPPING", "NO STANDING", "NO PARKING",
    "CLEARWAY", "LOADING ZONE", "BUS ZONE", "TAXI ZONE",
    "PERMIT ZONE", "MAIL ZONE", "WORKS ZONE", "DROP OFF",
    "TOW AWAY", "DISABLED",
]

# Single-word strong indicators (still strong, just one word)
STRONG_SINGLE = [
    "CLEARWAY", "LOADING", "PERMIT", "TICKET", "METER", "DISABLED",
]

# Weak alone — only meaningful in combination. 0.5 points each, capped.
WEAK_KEYWORDS = [
    "MON", "TUE", "TUES", "WED", "THU", "THUR", "THURS", "FRI", "SAT", "SUN",
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
    "AM", "PM",
    "MINUTE", "MINUTES", "HOUR", "HOURS", "MIN", "HRS",
]

# "1P", "2P", "4P", "1/4P", "1/2P" — Australian P-code (time-limited parking).
P_CODE_RE = re.compile(r"\b(?:1/4|1/2|1|2|3|4)P\b", re.IGNORECASE)

# A real time range, e.g. "8:30-18:30", "08:30-6:30PM", "8 AM - 12 PM".
# Requires a colon-or-dot separator on at least one side, so plain digit
# pairs like "1-2" don't trigger.
TIME_RANGE_RE = re.compile(
    r"\b\d{1,2}\s*[:.]\s*\d{2}\s*(?:AM|PM)?\s*[-–—]\s*"
    r"\d{1,2}\s*(?:[:.]\s*\d{2})?\s*(?:AM|PM)?\b",
    re.IGNORECASE,
)

# Default minimum per-word Tesseract confidence to keep.
WORD_CONF_FLOOR = 40

# Score required to flag an image as containing a parking sign.
PARKING_FLAG_SCORE = 3.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WordBox:
    text: str
    conf: int       # 0 - 100
    x: int
    y: int
    w: int
    h: int


@dataclass
class OCRReading:
    text: str = ""                   # Joined high-confidence words.
    raw_text: str = ""               # Tesseract's raw output (all confs).
    word_boxes: list = field(default_factory=list)  # WordBox list
    keywords_found: list = field(default_factory=list)
    keyword_score: float = 0.0
    has_time_range: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def _preprocess_for_ocr(img_bgr: np.ndarray) -> np.ndarray:
    """Make text easier for Tesseract on a wide street scene.

    Pipeline: grayscale → 2× upscale → CLAHE local-contrast.

    Critically we do NOT binarize (adaptive_threshold) anymore. On a
    640-1280px-wide streetscape with small distant signs (often 50-80px
    tall), thresholding destroys the small high-frequency features that
    distinguish '2P' from '8P' or 'NO STOPPING' from a wall. Tesseract's
    own internal binarizer handles this much better than our global one.
    Verified: with this preprocessing Tesseract picks up '2P' at conf=79
    in our regression image, vs conf=0 with adaptive_threshold.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # Always upscale 2x for street scenes where signs are small.
    gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return gray


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def ocr_image(img_bgr: np.ndarray, psm: int = 11,
              conf_floor: int = WORD_CONF_FLOOR) -> OCRReading:
    """Run Tesseract on the image and return the high-confidence words plus
    their bounding boxes plus the parking-sign keyword score.

    `psm=11` is "sparse text" — appropriate for street-scene images where
    text appears in scattered patches (signs on poles, shop fronts, etc.)
    rather than as a dense block. PSM 6 ("uniform block") was the earlier
    default but it forces Tesseract to interpret the entire frame as one
    paragraph, producing gibberish from texture/noise.

    `conf_floor` (0-100) drops words Tesseract isn't confident about.
    """
    if not _TESSERACT_OK:
        return OCRReading(error="pytesseract is not installed")

    try:
        prepped = _preprocess_for_ocr(img_bgr)
        config = (f"--psm {psm} -c "
                  "tessedit_char_whitelist="
                  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                  ":-/. ")
        # Per-word data (text, conf, bbox)
        data = pytesseract.image_to_data(prepped, config=config, output_type=Output.DICT)
    except pytesseract.TesseractNotFoundError:
        return OCRReading(error="tesseract binary not installed (see README)")
    except Exception as exc:
        return OCRReading(error=f"OCR failed: {exc}")

    # Track scale factor (we resized in preprocessing, so word bboxes are in
    # the resized coordinate space). We need to project them back to the
    # original image coordinates.
    h_orig, w_orig = img_bgr.shape[:2]
    h_pre, w_pre = prepped.shape[:2]
    sx = w_orig / w_pre if w_pre else 1.0
    sy = h_orig / h_pre if h_pre else 1.0

    word_boxes: list[WordBox] = []
    raw_words: list[str] = []
    high_conf_words: list[str] = []
    n = len(data.get("text", []))
    for i in range(n):
        word = (data["text"][i] or "").strip()
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if not word:
            continue
        raw_words.append(word)
        if conf >= conf_floor:
            high_conf_words.append(word)
            word_boxes.append(WordBox(
                text=word, conf=conf,
                x=int(data["left"][i] * sx),
                y=int(data["top"][i] * sy),
                w=int(data["width"][i] * sx),
                h=int(data["height"][i] * sy),
            ))

    text = " ".join(high_conf_words)
    raw_text = " ".join(raw_words)
    score, kws = score_text_for_parking(text)
    has_time = bool(TIME_RANGE_RE.search(text))
    return OCRReading(
        text=text, raw_text=raw_text,
        word_boxes=word_boxes,
        keywords_found=kws,
        keyword_score=score,
        has_time_range=has_time,
    )


# ---------------------------------------------------------------------------
# Scoring (word-boundary, tiered)
# ---------------------------------------------------------------------------

def _has_word(text_upper: str, kw: str) -> bool:
    """Word-boundary search. So 'MON' matches 'MON' or 'MON-FRI' but not
    'MONITORING'."""
    pat = r"\b" + re.escape(kw) + r"\b"
    return re.search(pat, text_upper) is not None


def score_text_for_parking(text: str) -> tuple[float, list[str]]:
    """Tiered scoring with word-boundary matching. Threshold for flagging
    is 3.0 (defined as `PARKING_FLAG_SCORE` above):

      - Any single STRONG keyword: +3 (alone passes the threshold).
      - Any P-code (1P / 2P / 4P / 1/4P / 1/2P): +3.
      - A time range ("8:30-18:30" or similar): +2.
      - WEAK keywords (MON / TUE / AM / PM / ...): +0.5 each, capped at 4
        weaks (so noise spelling out "AM PM MON FRI" by accident lands
        at 2.0 - below the threshold).
    """
    text_upper = text.upper()
    found: list[str] = []
    score = 0.0

    # Strong multi-word keywords (e.g. "NO STOPPING")
    for kw in STRONG_KEYWORDS:
        # Multi-word keywords use word boundaries on both ends.
        pat = r"\b" + re.escape(kw) + r"\b"
        if re.search(pat, text_upper):
            found.append(kw)
            score += 3.0

    # Strong single-word keywords (e.g. "CLEARWAY") — only count if not
    # already matched as part of a multi-word strong (e.g. "LOADING" is
    # part of "LOADING ZONE"; we don't want to double-count).
    for kw in STRONG_SINGLE:
        if any(kw in s for s in found):  # already covered by a multi-word
            continue
        if _has_word(text_upper, kw):
            found.append(kw)
            score += 3.0

    # P-codes
    for m in P_CODE_RE.findall(text):
        # Normalise the matched text and dedupe
        token = m.upper()
        if token not in found:
            found.append(token)
            score += 3.0

    # Time range
    if TIME_RANGE_RE.search(text):
        found.append("TIME_RANGE")
        score += 2.0

    # Weak keywords (capped contribution)
    weak_hits = 0
    for kw in WEAK_KEYWORDS:
        if _has_word(text_upper, kw):
            found.append(kw)
            weak_hits += 1
    score += min(weak_hits, 4) * 0.5

    return score, found


# ---------------------------------------------------------------------------
# Annotation: draw boxes around what Tesseract actually read
# ---------------------------------------------------------------------------

def annotate_text(img_bgr: np.ndarray, reading: OCRReading,
                  highlight_keywords: bool = True) -> np.ndarray:
    """Draw boxes around the high-confidence words Tesseract returned.

    A word that contributed to the parking-keyword score is drawn in
    green; other words are drawn in a softer grey so the user can see
    what Tesseract picked up overall."""
    out = img_bgr.copy()
    if not reading.word_boxes:
        return out
    keyword_text_set = {kw.upper() for kw in reading.keywords_found}
    for wb in reading.word_boxes:
        is_kw = wb.text.upper() in keyword_text_set
        colour = (40, 200, 40) if (is_kw and highlight_keywords) else (180, 180, 180)
        thickness = 2 if (is_kw and highlight_keywords) else 1
        cv2.rectangle(out, (wb.x, wb.y), (wb.x + wb.w, wb.y + wb.h),
                      colour, thickness)
        if is_kw and highlight_keywords:
            label = f"{wb.text} ({wb.conf})"
            cv2.putText(out, label, (wb.x, max(15, wb.y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1, cv2.LINE_AA)
    return out


def save_annotated_text(image_path, reading: OCRReading, out_path) -> None:
    img = cv2.imread(str(image_path))
    if img is None:
        return
    out = annotate_text(img, reading)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), out)
