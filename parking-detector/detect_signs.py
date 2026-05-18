"""
detect_signs.py
---------------
OCR pipeline for Australian street-parking signs.

Backends:
  - 'rapid' (default): RapidOCR — PaddleOCR PP-OCR models exported to
    ONNX. Detection-based, so it locates text regions itself; no need
    for the upscale + CLAHE dance Tesseract required for sparse
    streetscape text. Pure-pip dependency (rapidocr-onnxruntime),
    bundled models, no `paddlepaddle`/`torch` install.
  - 'tesseract' (fallback): the original pipeline. Kept around for A/B
    comparison and for environments where shipping the ONNX runtime
    isn't viable.

Pick a backend with the OCR_BACKEND env var ('rapid' | 'tesseract').

Pipeline:
  1. Run the chosen backend on the raw image — neither needs OpenCV
     preprocessing for parking-sign text. (Tesseract path still does
     a conditional 2× upscale + CLAHE because that's what made it
     usable on Street View thumbnails; the Rapid path skips it.)
  2. Drop low-confidence words (<40 on Tesseract's 0-100 scale,
     <0.40 on RapidOCR's 0-1 scale).
  3. Score the joined high-confidence text against a tiered keyword
     dictionary using WORD-BOUNDARY matching.
  4. Return the score along with per-region bounding boxes so the HTML
     contact sheet can draw rectangles over what the model actually
     read.

Scoring is unchanged across backends — it operates on the joined text.
See `score_text_for_parking()` for the tiers.
"""
from __future__ import annotations

import os
import re
import threading
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

try:
    from rapidocr_onnxruntime import RapidOCR
    _RAPID_OK = True
except ImportError:
    _RAPID_OK = False


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

OCR_BACKEND = os.getenv("OCR_BACKEND", "rapid").strip().lower() or "rapid"

# RapidOCR engine is lazily constructed on first use (model load is ~200ms).
# Wrapped in a lock because parking_check.py drives OCR through a
# ThreadPoolExecutor and the engine's internal session isn't documented as
# threadsafe.
_rapid_engine: Optional["RapidOCR"] = None
_rapid_lock = threading.Lock()


def _get_rapid_engine() -> "RapidOCR":
    global _rapid_engine
    if _rapid_engine is None:
        with _rapid_lock:
            if _rapid_engine is None:
                _rapid_engine = RapidOCR()
    return _rapid_engine


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

# Default minimum per-word Tesseract confidence to keep (0-100 scale).
WORD_CONF_FLOOR = 40

# Default minimum RapidOCR region confidence (0-1 scale).
RAPID_CONF_FLOOR = 0.40

# Score required to flag an image as containing a parking sign.
PARKING_FLAG_SCORE = 3.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WordBox:
    text: str
    conf: int       # 0-100. RapidOCR's 0-1 score is rescaled.
    x: int
    y: int
    w: int
    h: int


@dataclass
class OCRReading:
    text: str = ""                   # Joined high-confidence words/regions.
    raw_text: str = ""               # Raw OCR output (all confs).
    word_boxes: list = field(default_factory=list)  # WordBox list
    keywords_found: list = field(default_factory=list)
    keyword_score: float = 0.0
    has_time_range: bool = False
    error: Optional[str] = None
    backend: str = ""                # 'rapid' or 'tesseract'


# ---------------------------------------------------------------------------
# Tesseract preprocessing (only used by the tesseract backend)
# ---------------------------------------------------------------------------

UPSCALE_SKIP_WIDTH = 2600


def _preprocess_for_tesseract(img_bgr: np.ndarray) -> np.ndarray:
    """Make text easier for Tesseract on a wide street scene.

    Pipeline: grayscale → conditional upscale → CLAHE local-contrast.

    Upscale logic:
      - If input width < UPSCALE_SKIP_WIDTH (2600 px), 2× upscale. This
        covers thumbnails (1024 → 2048) AND tile-stitched z4 crops
        (1820 → 3640). Tesseract gets more pixels per glyph on the
        small distant signs that dominate parking-OCR work.
      - If input width >= 2600 px, skip the upscale. Doubling those
        pushes the buffer past Tesseract's reasonable working size and
        triggers >40s OCR runs.

    Not used by the RapidOCR backend — that model's detection head
    handles streetscape scale variation natively.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if w < UPSCALE_SKIP_WIDTH:
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return gray


# ---------------------------------------------------------------------------
# Public OCR entrypoint — dispatches to selected backend
# ---------------------------------------------------------------------------

def ocr_image(img_bgr: np.ndarray, conf_floor: Optional[float] = None) -> OCRReading:
    """Run the configured OCR backend on the image and return a scored
    OCRReading.

    `conf_floor` is interpreted relative to the backend's native scale:
      - tesseract: int 0-100 (default 40)
      - rapid:     float 0-1  (default 0.40)
    For convenience we accept either; values >1 are treated as percent
    and divided by 100 for the rapid backend.
    """
    backend = OCR_BACKEND
    if backend == "rapid":
        if not _RAPID_OK:
            return OCRReading(
                error="rapidocr-onnxruntime is not installed (pip install it, "
                      "or set OCR_BACKEND=tesseract)",
                backend="rapid",
            )
        floor: float
        if conf_floor is None:
            floor = RAPID_CONF_FLOOR
        elif conf_floor > 1:
            floor = conf_floor / 100.0
        else:
            floor = float(conf_floor)
        return _ocr_image_rapid(img_bgr, conf_floor=floor)

    if backend == "tesseract":
        floor_int = int(conf_floor) if conf_floor is not None else WORD_CONF_FLOOR
        if floor_int <= 1:
            floor_int = int(floor_int * 100)
        return _ocr_image_tesseract(img_bgr, psm=11, conf_floor=floor_int)

    return OCRReading(error=f"unknown OCR_BACKEND={backend!r}", backend=backend)


# ---------------------------------------------------------------------------
# RapidOCR backend
# ---------------------------------------------------------------------------

def _ocr_image_rapid(img_bgr: np.ndarray, conf_floor: float) -> OCRReading:
    """Run RapidOCR (PP-OCR ONNX) and adapt output to OCRReading.

    RapidOCR returns `[(quad, text, conf), ...]` where `quad` is four
    [x,y] points (clockwise from top-left) and `conf` is 0-1.

    We collapse each quad to its axis-aligned bounding box for WordBox,
    multiply conf to fit the existing 0-100 contract, drop low-confidence
    regions, then feed the joined text into the same scorer Tesseract
    uses. This keeps the downstream `annotate_text` and call sites in
    `parking_check.py` working without modification.
    """
    try:
        engine = _get_rapid_engine()
        result, _elapsed = engine(img_bgr)
    except Exception as exc:
        return OCRReading(error=f"RapidOCR failed: {exc}", backend="rapid")

    if not result:
        return OCRReading(text="", raw_text="", backend="rapid")

    word_boxes: list[WordBox] = []
    raw_words: list[str] = []
    high_conf_words: list[str] = []
    for quad, text, conf in result:
        text = (text or "").strip()
        if not text:
            continue
        raw_words.append(text)
        try:
            conf = float(conf)
        except (ValueError, TypeError):
            conf = 0.0
        if conf < conf_floor:
            continue
        # quad is a list of 4 [x,y] floats; collapse to AABB.
        xs = [int(p[0]) for p in quad]
        ys = [int(p[1]) for p in quad]
        x = min(xs); y = min(ys)
        w = max(xs) - x
        h = max(ys) - y
        word_boxes.append(WordBox(
            text=text, conf=int(round(conf * 100)),
            x=x, y=y, w=max(1, w), h=max(1, h),
        ))
        high_conf_words.append(text)

    text_joined = " ".join(high_conf_words)
    raw_text = " ".join(raw_words)
    score, kws = score_text_for_parking(text_joined)
    return OCRReading(
        text=text_joined, raw_text=raw_text,
        word_boxes=word_boxes,
        keywords_found=kws,
        keyword_score=score,
        has_time_range=bool(TIME_RANGE_RE.search(text_joined)),
        backend="rapid",
    )


# ---------------------------------------------------------------------------
# Tesseract backend
# ---------------------------------------------------------------------------

def _ocr_image_tesseract(img_bgr: np.ndarray, psm: int = 11,
                         conf_floor: int = WORD_CONF_FLOOR) -> OCRReading:
    """Run Tesseract on the image and return high-confidence words plus
    their bounding boxes plus the parking-sign keyword score.

    `psm=11` is "sparse text" — appropriate for street-scene images where
    text appears in scattered patches rather than as a dense block.
    """
    if not _TESSERACT_OK:
        return OCRReading(error="pytesseract is not installed", backend="tesseract")

    try:
        prepped = _preprocess_for_tesseract(img_bgr)
        config = (f"--psm {psm} -c "
                  "tessedit_char_whitelist="
                  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                  ":-/. ")
        data = pytesseract.image_to_data(prepped, config=config, output_type=Output.DICT)
    except pytesseract.TesseractNotFoundError:
        return OCRReading(error="tesseract binary not installed (see README)",
                          backend="tesseract")
    except Exception as exc:
        return OCRReading(error=f"OCR failed: {exc}", backend="tesseract")

    # Project word bboxes back to original image coords (we resized in
    # preprocessing).
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
    return OCRReading(
        text=text, raw_text=raw_text,
        word_boxes=word_boxes,
        keywords_found=kws,
        keyword_score=score,
        has_time_range=bool(TIME_RANGE_RE.search(text)),
        backend="tesseract",
    )


# ---------------------------------------------------------------------------
# Scoring (word-boundary, tiered)
# ---------------------------------------------------------------------------

def _has_word(text_upper: str, kw: str) -> bool:
    """Word-boundary search. So 'MON' matches 'MON' or 'MON-FRI' but not
    'MONITORING'."""
    pat = r"\b" + re.escape(kw) + r"\b"
    return re.search(pat, text_upper) is not None


def _has_strong_keyword(text_upper: str, text_compact: str, kw: str) -> bool:
    """Strong-keyword match with two passes:

    1. Word-boundary search against the original text.
    2. Substring search against a space-collapsed version of the text,
       comparing to a space-collapsed keyword.

    Pass 2 covers RapidOCR's common behaviour of reading tightly-kerned
    sign text (e.g. 'NO PARKING') as a single token ('NOPARKING'). The
    STRONG keywords are specific enough multi-word phrases that
    substring matching here doesn't generate realistic false positives.
    """
    pat = r"\b" + re.escape(kw) + r"\b"
    if re.search(pat, text_upper):
        return True
    kw_compact = kw.replace(" ", "")
    return kw_compact in text_compact


def score_text_for_parking(text: str) -> tuple[float, list[str]]:
    """Tiered scoring with word-boundary matching. Threshold for flagging
    is 3.0 (defined as `PARKING_FLAG_SCORE` above):

      - Any single STRONG keyword: +3 (alone passes the threshold).
      - Any P-code (1P / 2P / 4P / 1/4P / 1/2P): +3.
      - A time range ("8:30-18:30" or similar): +2.
      - WEAK keywords (MON / TUE / AM / PM / ...): +0.5 each, capped at 4
        weaks (so noise spelling out "AM PM MON FRI" by accident lands
        at 2.0 — below the threshold).
    """
    text_upper = text.upper()
    text_compact = text_upper.replace(" ", "")
    found: list[str] = []
    score = 0.0

    # Strong multi-word keywords (e.g. "NO STOPPING"). Also matches the
    # space-collapsed form ("NOSTOPPING") for RapidOCR concatenation.
    for kw in STRONG_KEYWORDS:
        if _has_strong_keyword(text_upper, text_compact, kw):
            found.append(kw)
            score += 3.0

    # Strong single-word keywords (e.g. "CLEARWAY") — only count if not
    # already matched as part of a multi-word strong (e.g. "LOADING" is
    # part of "LOADING ZONE"; we don't want to double-count).
    for kw in STRONG_SINGLE:
        if any(kw in s for s in found):
            continue
        if _has_word(text_upper, kw):
            found.append(kw)
            score += 3.0

    # P-codes
    for m in P_CODE_RE.findall(text):
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
# Annotation: draw boxes around what OCR actually read
# ---------------------------------------------------------------------------

def _word_matches_any_keyword(word_upper: str, keywords_upper: set[str]) -> bool:
    """A region is highlighted if it equals any found keyword OR is one of
    the tokens of a multi-word keyword.

    Tesseract returns one word per WordBox so single-token keywords match
    directly. RapidOCR may return a region containing multiple words
    (e.g. 'LOADING ZONE') — handled by direct equality. When RapidOCR
    splits a phrase into separate regions ('LOADING', 'ZONE'), each is
    matched against the tokens of every multi-word keyword.
    """
    for kw in keywords_upper:
        if word_upper == kw:
            return True
        if " " in kw and word_upper in kw.split():
            return True
    return False


def annotate_text(img_bgr: np.ndarray, reading: OCRReading,
                  highlight_keywords: bool = True) -> np.ndarray:
    """Draw boxes around the high-confidence regions OCR returned.

    A region that contributed to the parking-keyword score is drawn in
    green; other regions are drawn in a softer grey so the user can see
    what OCR picked up overall."""
    out = img_bgr.copy()
    if not reading.word_boxes:
        return out
    keyword_text_set = {kw.upper() for kw in reading.keywords_found}
    for wb in reading.word_boxes:
        is_kw = _word_matches_any_keyword(wb.text.upper(), keyword_text_set)
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
    from pathlib import Path
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), out)
