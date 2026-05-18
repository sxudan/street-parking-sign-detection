#!/usr/bin/env python3
"""
parking_check.py  (simple edition)
----------------------------------
Given a street address, find the parking signs near it. The algorithm is
deliberately dumb-and-thorough rather than clever-and-fragile:

    1. Geocode the address.
    2. Discover every distinct Street View pano within --radius metres
       (free metadata probes).
    3. From every pano, capture N headings as an evenly-spaced sweep
       (default 8). At each radius pano the sweep starts pointing at
       the address, so the very first frame is always aimed inwards.
    4. Run Tesseract OCR on every captured image.
    5. Score each image's text against parking-sign keywords ("1P",
       "2P", "MON-FRI", "AM/PM", time ranges, "ZONE", "STOPPING", ...).
    6. Build an HTML contact sheet, grouping images by pano, with the
       OCR text and parking-keyword highlights underneath each.

No vision API, no paid OCR. Only Google Maps (free tier covers
hundreds of lookups). Tesseract runs locally.

Usage:
    python parking_check.py "12 Smith Street, Fitzroy VIC 3065"
    python parking_check.py "12 Smith St" --radius 50          # scan 50 m
    python parking_check.py "12 Smith St" --radius 50 --pitches "0,10,-5"
    python parking_check.py "12 Smith St" --zoom 45:30:15      # manual zoom
    python parking_check.py "12 Smith St" --no-ocr             # capture only

Required environment variable (put it in .env next to this script):
    GOOGLE_MAPS_API_KEY  - Geocoding API + Street View Static API enabled
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from html import escape
from pathlib import Path
from typing import Optional

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Detection module is optional. If cv2 / pytesseract aren't installed, the
# script still works in capture-only mode (no OCR, no annotations).
_DETECT_OK = True
_DETECT_IMPORT_ERROR = ""
try:
    import detect_signs
except ImportError as _exc:
    _DETECT_OK = False
    _DETECT_IMPORT_ERROR = str(_exc)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
SV_METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
SV_IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"

# Unofficial / internal Google Maps thumbnail endpoint. Used by the Maps
# web client. Returns higher-resolution images than the Static API's free
# tier and does not require an API key. UNDOCUMENTED - Google can change
# or break this without notice. See README for ToS notes.
SV_THUMBNAIL_URL = "https://streetviewpixels-pa.googleapis.com/v1/thumbnail"

EARTH_RADIUS_M = 6_378_137.0

# Parking-keyword score threshold above which an image is highlighted.
# Imported from detect_signs so the two modules agree on the threshold.
PARKING_FLAG_SCORE = 3.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Pano:
    pano_id: str
    lat: float
    lng: float
    date: Optional[str]
    distance_m: float


@dataclass
class CapturedImage:
    purpose: str             # "sweep" | "radius_scan" | "manual_zoom"
    pano_id: str
    pano_date: Optional[str]
    pano_distance_m: float   # distance from address (0 = address pano)
    heading: float
    pitch: float
    fov: float
    lat: float
    lng: float
    file_path: str
    ocr_text: str = ""
    keywords_found: list = field(default_factory=list)
    keyword_score: float = 0.0


@dataclass
class CaptureReport:
    address_query: str
    resolved_address: str
    lat: float
    lng: float
    pano_id: Optional[str]
    pano_date: Optional[str]
    images: list[CapturedImage] = field(default_factory=list)
    ocr_used: bool = False


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def geocode(address: str, key: str) -> tuple[float, float, str, list]:
    """Returns (lat, lng, formatted_address, address_components).
    The components list is what we use to know which street the address is on."""
    r = requests.get(GEOCODE_URL, params={"address": address, "key": key}, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "OK" or not body.get("results"):
        raise RuntimeError(
            f"Geocode failed: status={body.get('status')} "
            f"error={body.get('error_message')}"
        )
    top = body["results"][0]
    loc = top["geometry"]["location"]
    return (loc["lat"], loc["lng"],
            top.get("formatted_address", address),
            top.get("address_components", []))


def reverse_geocode_components(lat: float, lng: float, key: str) -> list:
    """Reverse-geocode a coordinate and return the first result's
    address_components. Used to find which street a pano sits on."""
    r = requests.get(GEOCODE_URL, params={
        "latlng": f"{lat},{lng}",
        "key": key,
    }, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "OK" or not body.get("results"):
        return []
    return body["results"][0].get("address_components", [])


def get_route_names(components: list) -> set[str]:
    """Extract the street-name variants (long_name and short_name) from an
    address_components list. So 'Osborne Street' vs 'Osborne St' both end
    up in the set, ready for case-insensitive comparison."""
    names: set[str] = set()
    for c in components:
        if "route" in c.get("types", []):
            for key in ("long_name", "short_name"):
                v = (c.get(key) or "").strip().lower()
                if v:
                    names.add(v)
    return names


def filter_panos_same_street(panos: list, addr_components: list, key: str,
                             log) -> list:
    """Keep only panos whose reverse-geocoded street matches the address's
    street. The address pano (distance < 1m) is always kept regardless."""
    addr_streets = get_route_names(addr_components)
    if not addr_streets:
        log("      (no route component on address; keeping all panos)")
        return panos
    log(f"      address street(s): {sorted(addr_streets)}")
    out: list = []
    for p in panos:
        if p.distance_m < 1.0:
            out.append(p)
            log(f"      KEEP  {p.pano_id[:14]}.. (address pano, always kept)")
            continue
        comps = reverse_geocode_components(p.lat, p.lng, key)
        pano_streets = get_route_names(comps)
        match = pano_streets & addr_streets
        if match:
            out.append(p)
            log(f"      KEEP  {p.pano_id[:14]}.. at {p.distance_m:.1f}m  "
                f"(matches {sorted(match)})")
        else:
            label = sorted(pano_streets) if pano_streets else "[no route]"
            log(f"      DROP  {p.pano_id[:14]}.. at {p.distance_m:.1f}m  "
                f"(street: {label})")
    return out


def offset_metres(lat: float, lng: float, north_m: float, east_m: float) -> tuple[float, float]:
    dlat = (north_m / EARTH_RADIUS_M) * (180.0 / math.pi)
    dlng = (east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat)))) * (180.0 / math.pi)
    return lat + dlat, lng + dlng


def bearing_deg(from_lat: float, from_lng: float,
                to_lat: float, to_lng: float) -> float:
    phi1 = math.radians(from_lat)
    phi2 = math.radians(to_lat)
    dlng = math.radians(to_lng - from_lng)
    x = math.sin(dlng) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(dlng))
    brng = math.degrees(math.atan2(x, y))
    return (brng + 360.0) % 360.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Street View
# ---------------------------------------------------------------------------

def streetview_metadata(lat: float, lng: float, key: str, radius: int = 50) -> dict:
    r = requests.get(SV_METADATA_URL, params={
        "location": f"{lat},{lng}",
        "radius": radius,
        "source": "outdoor",
        "key": key,
    }, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "OK":
        return {}
    return body


def discover_panos(centre_lat: float, centre_lng: float, radius_m: float,
                   key: str, *, ring_step_m: int = 15,
                   points_per_ring: int = 12, snap_radius_m: int = 10,
                   max_workers: int = 8,
                   ) -> list[Pano]:
    """Find every distinct Street View pano within radius_m of the centre.
    Metadata calls are FREE; this function uses ~36 probes for radius=50.

    Probes run in parallel (default 8 workers), since each metadata
    request is an independent HTTP GET.
    """
    seen: dict[str, Pano] = {}

    def make_pano_from_meta(meta: dict, centre_lat: float, centre_lng: float) -> Optional[Pano]:
        pid = meta.get("pano_id")
        loc = meta.get("location") or {}
        if not pid:
            return None
        pano_lat = loc.get("lat")
        pano_lng = loc.get("lng")
        if pano_lat is None or pano_lng is None:
            return None
        d = haversine_m(centre_lat, centre_lng, float(pano_lat), float(pano_lng))
        return Pano(
            pano_id=pid,
            lat=float(pano_lat),
            lng=float(pano_lng),
            date=meta.get("date"),
            distance_m=d,
        )

    # Address pano (centre) probe — done first, with a generous radius.
    centre_meta = streetview_metadata(centre_lat, centre_lng, key, radius=50)
    if centre_meta:
        p = make_pano_from_meta(centre_meta, centre_lat, centre_lng)
        if p:
            seen[p.pano_id] = p

    if radius_m <= 0:
        return sorted(seen.values(), key=lambda p: p.distance_m)

    # Build ring probe coordinates
    rings = []
    r = ring_step_m
    while r <= radius_m + 0.5:
        rings.append(r)
        r += ring_step_m
    if not rings:
        rings.append(int(radius_m))

    probe_coords: list[tuple[float, float]] = []
    for ring_r in rings:
        for i in range(points_per_ring):
            angle_deg = (i * 360.0 / points_per_ring) % 360.0
            east_m = ring_r * math.sin(math.radians(angle_deg))
            north_m = ring_r * math.cos(math.radians(angle_deg))
            probe_coords.append(offset_metres(centre_lat, centre_lng, north_m, east_m))

    # Parallel probes
    def probe_one(coord):
        plat, plng = coord
        return streetview_metadata(plat, plng, key, radius=snap_radius_m)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for meta in ex.map(probe_one, probe_coords):
            if not meta:
                continue
            p = make_pano_from_meta(meta, centre_lat, centre_lng)
            if not p or p.pano_id in seen:
                continue
            if p.distance_m > radius_m + 5.0:
                continue
            seen[p.pano_id] = p

    return sorted(seen.values(), key=lambda p: p.distance_m)


def fetch_streetview_image(*, heading: float, pitch: float, fov: float,
                           size: str, key: str, out_path: Path,
                           pano_id: Optional[str] = None,
                           lat: Optional[float] = None,
                           lng: Optional[float] = None) -> bool:
    """Fetch via the official Street View Static API. Costs $0.007/image.
    Free tier capped at 640x640. Supports precise FOV control."""
    params = {
        "size": size,
        "heading": f"{heading:.2f}",
        "pitch": f"{pitch:.2f}",
        "fov": f"{fov:.2f}",
        "source": "outdoor",
        "return_error_code": "true",
        "key": key,
    }
    if pano_id:
        params["pano"] = pano_id
    elif lat is not None and lng is not None:
        params["location"] = f"{lat},{lng}"
    else:
        raise ValueError("fetch_streetview_image: pass pano_id or (lat, lng)")
    r = requests.get(SV_IMAGE_URL, params=params, timeout=30)
    if r.status_code != 200:
        return False
    if len(r.content) < 3_000:  # Google's "no imagery" placeholder
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return True


def fetch_streetview_thumbnail(*, pano_id: str, heading: float, pitch: float,
                               width: int, height: int, out_path: Path,
                               thumb_variant: int = 3) -> bool:
    """Fetch via the unofficial streetviewpixels-pa thumbnail endpoint.

    Pros:
      - Higher resolution than Static API free tier (you can request e.g.
        1280x720 or larger).
      - No per-image charge.
      - No API key.

    Cons:
      - UNDOCUMENTED, internal Google Maps endpoint. Could break any time.
      - No FOV parameter. The angular field of view is fixed by the
        `thumb_variant` and the requested aspect ratio. So --fovs is
        ignored when this backend is in use.
      - Maps Platform ToS gray area: low-volume personal use is unlikely
        to attract attention; bulk / commercial use isn't safe here.
      - Google may rate-limit by IP for high volumes.

    Required: a real pano_id. lat/lng won't work here - Google's
    thumbnail endpoint addresses panos directly, not coordinates.
    """
    params = {
        "output": "thumbnail",
        "cb_client": "maps_sv.tactile.gps",
        "panoid": pano_id,
        "w": str(int(width)),
        "h": str(int(height)),
        "thumb": str(int(thumb_variant)),
        "yaw": f"{heading:.4f}",
        "pitch": f"{pitch:.4f}",
    }
    try:
        r = requests.get(SV_THUMBNAIL_URL, params=params, timeout=30)
    except requests.RequestException:
        return False
    if r.status_code != 200:
        return False
    if len(r.content) < 3_000:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    return True


# ---------------------------------------------------------------------------
# Capture: from each pano, sweep N headings (and optionally M pitches)
# ---------------------------------------------------------------------------

def parse_pitch_list(s: str) -> list[float]:
    """Parse "0,10,-5" -> [0.0, 10.0, -5.0]."""
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out or [0.0]


def parse_fov_list(s: str) -> list[int]:
    """Parse "80,30" -> [80, 30]."""
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        v = int(float(part))
        # Street View Static API accepts FOV 10-120.
        v = max(10, min(120, v))
        out.append(v)
    return out or [80]


def parse_size(s: str) -> tuple[int, int]:
    """Parse 'WIDTHxHEIGHT' (e.g. '1280x720') -> (1280, 720)."""
    s = s.strip().lower().replace("×", "x")
    parts = s.split("x")
    if len(parts) != 2:
        raise ValueError(f"size must be WxH, got {s!r}")
    return int(parts[0]), int(parts[1])


def parse_zoom_spec(spec: str) -> tuple[float, float, float]:
    """Parse 'HEADING:FOV:PITCH' (FOV defaults 30, PITCH defaults 0)."""
    parts = spec.split(":")
    heading = float(parts[0])
    fov = float(parts[1]) if len(parts) > 1 and parts[1] else 30.0
    pitch = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
    return heading, fov, pitch


@dataclass
class _FetchTask:
    """One concrete (pano, heading, pitch, fov) capture to perform."""
    pano: Pano
    heading: float
    pitch: float
    fov: int
    fname: str
    purpose: str


def _execute_fetch_tasks(tasks: list[_FetchTask], *, size: str, key: str,
                         images_dir: Path, use_thumbnail: bool,
                         thumbnail_size: tuple[int, int],
                         max_workers: int, log,
                         ) -> list[CapturedImage]:
    """Run all fetch tasks in parallel via a thread pool. Returns the
    successful CapturedImage objects."""

    def do_one(task: _FetchTask) -> Optional[CapturedImage]:
        fpath = images_dir / task.fname
        if use_thumbnail:
            w, ht = thumbnail_size
            ok = fetch_streetview_thumbnail(
                pano_id=task.pano.pano_id, heading=task.heading,
                pitch=task.pitch, width=w, height=ht, out_path=fpath,
            )
            recorded_fov = 0
        else:
            ok = fetch_streetview_image(
                pano_id=task.pano.pano_id, heading=task.heading,
                pitch=task.pitch, fov=task.fov, size=size, key=key,
                out_path=fpath,
            )
            recorded_fov = task.fov
        if not ok:
            return None
        return CapturedImage(
            purpose=task.purpose, pano_id=task.pano.pano_id,
            pano_date=task.pano.date,
            pano_distance_m=task.pano.distance_m,
            heading=task.heading, pitch=task.pitch, fov=recorded_fov,
            lat=task.pano.lat, lng=task.pano.lng,
            file_path=str(fpath),
        )

    captures: list[CapturedImage] = []
    saved = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for result in ex.map(do_one, tasks):
            if result is not None:
                captures.append(result)
                saved += 1
            else:
                failed += 1
    log(f"      fetched {saved}/{len(tasks)} ({failed} no-imagery)")
    return captures


def capture_pano(pano: Pano, headings: list[float], pitches: list[float],
                 fovs: list[int], size: str, key: str, images_dir: Path,
                 purpose: str, name_prefix: str, log,
                 use_thumbnail: bool = False,
                 thumbnail_size: tuple[int, int] = (1280, 720),
                 ) -> list[CapturedImage]:
    """Capture every (heading, pitch, fov) combo from one pano.

    If `use_thumbnail` is True, route through the unofficial thumbnail
    endpoint instead of the Static API. In that mode `fovs` is ignored
    (the thumbnail endpoint has no FOV parameter) and `thumbnail_size`
    sets the output WxH.
    """
    out: list[CapturedImage] = []
    # When using the thumbnail backend, we collapse the FOV loop to a
    # single iteration (the endpoint doesn't take FOV).
    effective_fovs = [0] if use_thumbnail else fovs

    for h in headings:
        h = h % 360.0
        if h >= 359.995:
            h = 0.0
        for p in pitches:
            for fov in effective_fovs:
                if use_thumbnail:
                    w, ht = thumbnail_size
                    fname = (f"{name_prefix}_h{int(round(h)):03d}"
                             f"_p{int(round(p)):+03d}_thumb.jpg")
                else:
                    fname = (f"{name_prefix}_h{int(round(h)):03d}"
                             f"_p{int(round(p)):+03d}"
                             f"_f{int(round(fov)):03d}.jpg")
                fpath = images_dir / fname

                if use_thumbnail:
                    w, ht = thumbnail_size
                    ok = fetch_streetview_thumbnail(
                        pano_id=pano.pano_id, heading=h, pitch=p,
                        width=w, height=ht, out_path=fpath,
                    )
                    recorded_fov = 0  # unknown
                else:
                    ok = fetch_streetview_image(
                        pano_id=pano.pano_id, heading=h, pitch=p, fov=fov,
                        size=size, key=key, out_path=fpath,
                    )
                    recorded_fov = fov

                if ok:
                    out.append(CapturedImage(
                        purpose=purpose, pano_id=pano.pano_id,
                        pano_date=pano.date, pano_distance_m=pano.distance_m,
                        heading=h, pitch=p, fov=recorded_fov,
                        lat=pano.lat, lng=pano.lng, file_path=str(fpath),
                    ))
                    log(f"      saved {fname}")
                else:
                    log(f"      (no imagery {fname})")
    return out


# ---------------------------------------------------------------------------
# OCR pass over every captured image
# ---------------------------------------------------------------------------

def ocr_and_annotate_all(images: list[CapturedImage], annotated_dir: Path,
                          do_annotate: bool, log,
                          max_workers: Optional[int] = None,
                          ) -> tuple[int, dict[str, str]]:
    """Run Tesseract on every image in parallel. Tesseract's C++ work
    releases the GIL during OCR, so threads do scale on multi-core boxes.

    Returns (flagged_count, annotated_paths_dict).
    """
    if not _DETECT_OK:
        log(f"      (OCR unavailable: {_DETECT_IMPORT_ERROR})")
        return 0, {}
    import cv2

    if max_workers is None:
        max_workers = max(1, (os.cpu_count() or 4))

    annotated: dict[str, str] = {}
    flagged_count = 0
    # We mutate `img` in place inside the worker so the caller sees results
    # back on its CapturedImage objects.
    def process_one(img: CapturedImage) -> tuple[bool, Optional[tuple[str, str]]]:
        bgr = cv2.imread(img.file_path)
        if bgr is None:
            return False, None
        result = detect_signs.ocr_image(bgr)
        img.ocr_text = result.text or (result.error or "")
        img.keywords_found = result.keywords_found
        img.keyword_score = result.keyword_score
        flag = result.keyword_score >= PARKING_FLAG_SCORE
        ann_pair: Optional[tuple[str, str]] = None
        if do_annotate and result.word_boxes:
            ann_path = annotated_dir / Path(img.file_path).name
            ann_path.parent.mkdir(parents=True, exist_ok=True)
            ann_img = detect_signs.annotate_text(bgr, result)
            cv2.imwrite(str(ann_path), ann_img)
            ann_pair = (img.file_path, str(ann_path))
        return flag, ann_pair

    log(f"      OCR'ing {len(images)} images via {max_workers} workers...")
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for img, (flag, ann_pair) in zip(images, ex.map(process_one, images)):
            if flag:
                flagged_count += 1
            if ann_pair:
                annotated[ann_pair[0]] = ann_pair[1]

    log(f"      OCR done: {flagged_count}/{len(images)} flagged as parking-like")
    return flagged_count, annotated


# ---------------------------------------------------------------------------
# High-res tile upgrade for flagged images
# ---------------------------------------------------------------------------

def upgrade_flagged_with_tiles(
    images: list[CapturedImage],
    annotated_paths: dict[str, str],
    images_dir: Path,
    annotated_dir: Path,
    *,
    zoom: int = 4,
    max_upgrades: int = 3,
    log,
) -> int:
    """For each flagged image (up to `max_upgrades`, sorted by score desc),
    fetch a high-resolution tile-stitched crop from streetviewpixels-pa
    /v1/tile, re-OCR it, and if the re-OCR score is at least as good as
    the thumbnail's, replace the image's file path + score in place.

    Returns the count of images successfully upgraded.
    """
    if not _DETECT_OK:
        log("      tile upgrade unavailable (cv2/pytesseract missing)")
        return 0
    try:
        import tile_fetcher
    except ImportError as exc:
        log(f"      tile_fetcher unavailable: {exc}")
        return 0
    import cv2

    # Pick the top N flagged by current score.
    flagged = [i for i in images if i.keyword_score >= PARKING_FLAG_SCORE]
    flagged.sort(key=lambda i: i.keyword_score, reverse=True)
    flagged = flagged[:max_upgrades]
    if not flagged:
        return 0

    log(f"      upgrading {len(flagged)} flagged image(s) to tile zoom {zoom}...")
    upgraded = 0
    for img in flagged:
        old_path = Path(img.file_path)
        new_name = old_path.stem + f"_z{zoom}_tile.jpg"
        new_path = images_dir / new_name

        cropped, stats = tile_fetcher.fetch_tile_crop(
            pano_id=img.pano_id, heading=img.heading, pitch=img.pitch,
            zoom=zoom, out_path=new_path, log=log,
        )
        if cropped is None or stats.get("tiles_fetched", 0) == 0:
            log(f"      [skip] {old_path.name}: no tiles fetched")
            continue

        # Re-OCR the high-res crop.
        bgr = cv2.imread(str(new_path))
        if bgr is None:
            log(f"      [skip] {old_path.name}: failed to read tile crop")
            continue
        new_reading = detect_signs.ocr_image(bgr)

        # Diagnostic line — always emit so we can see what the tile
        # crop actually contained, even when it scored low.
        kw_str = ",".join(new_reading.keywords_found[:5]) or "none"
        log(f"      tile-OCR    score={new_reading.keyword_score:.1f}  "
            f"kw=[{kw_str}]  text={new_reading.text[:120]!r}")

        # Replace the thumbnail with the high-res tile crop ONLY when
        # the tile OCR is at least as good. Score is keyword-presence-
        # based, so it should usually match or exceed the thumbnail
        # since the tile crop is sharper.
        if new_reading.keyword_score >= img.keyword_score:
            img.file_path = str(new_path)
            img.ocr_text = new_reading.text or img.ocr_text
            img.keywords_found = new_reading.keywords_found or img.keywords_found
            img.keyword_score = new_reading.keyword_score

            if new_reading.word_boxes:
                ann_path = annotated_dir / new_path.name
                ann_img = detect_signs.annotate_text(bgr, new_reading)
                cv2.imwrite(str(ann_path), ann_img)
                old_ann = annotated_paths.pop(str(old_path), None)
                if old_ann:
                    try:
                        Path(old_ann).unlink(missing_ok=True)
                    except Exception:
                        pass
                annotated_paths[str(new_path)] = str(ann_path)

            try:
                old_path.unlink(missing_ok=True)
            except Exception:
                pass

            upgraded += 1
            log(f"      [ok]   {old_path.name} -> {new_path.name}  "
                f"score {img.keyword_score:.1f}  kw={','.join(img.keywords_found[:5])}")
        else:
            # Tile OCR was worse than thumbnail. Don't replace, but
            # KEEP the tile crop on disk so the user can inspect it
            # — this case is almost certainly a bug in the crop math
            # or the OCR pipeline rather than a genuine quality
            # regression. The orphaned file lives next to the
            # thumbnail in images_dir/<job>/. Cleanup of unflagged
            # images runs later but only deletes images that aren't in
            # the report; this file doesn't appear in the report so it
            # would normally get cleaned up too. To make sure it
            # survives for debugging, we move it to a debug subdir.
            debug_dir = images_dir.parent / "tile_debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            try:
                debug_path = debug_dir / new_path.name
                new_path.replace(debug_path)
                kept_msg = f"saved to {debug_path}"
            except Exception as exc:
                kept_msg = f"could not relocate ({exc})"
                try:
                    new_path.unlink(missing_ok=True)
                except Exception:
                    pass
            log(f"      [keep] {old_path.name}: tile re-OCR scored "
                f"{new_reading.keyword_score:.1f} < thumbnail's {img.keyword_score:.1f} "
                f"({kept_msg})")

    return upgraded


# ---------------------------------------------------------------------------
# HTML contact sheet
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Parking sign report - {address}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
         margin: 0; padding: 24px; background: #f5f5f7; color: #1a1a1a; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a1a; color: #f0f0f0; }}
    .card, .meta {{ background: #2a2a2a; }}
    a {{ color: #6cb4ff; }}
  }}
  h1 {{ margin-top: 0; font-size: 22px; }}
  h2 {{ margin: 28px 0 10px; font-size: 17px; }}
  .meta {{ background: white; border-radius: 12px; padding: 16px 20px;
          margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
  .meta dl {{ margin: 0; display: grid; grid-template-columns: 170px 1fr; gap: 6px 12px; }}
  .meta dt {{ font-weight: 600; opacity: 0.75; }}
  .meta dd {{ margin: 0; }}
  .pano-block {{ margin-bottom: 32px; padding: 16px; background: rgba(0,0,0,0.03);
                 border-radius: 12px; }}
  @media (prefers-color-scheme: dark) {{
    .pano-block {{ background: rgba(255,255,255,0.04); }}
  }}
  .pano-header {{ font-size: 15px; font-weight: 600; margin-bottom: 12px; }}
  .pano-header .sub {{ font-weight: 400; opacity: 0.7; margin-left: 8px; font-size: 13px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
           gap: 12px; }}
  .card {{ background: white; border-radius: 10px; overflow: hidden;
          box-shadow: 0 1px 4px rgba(0,0,0,0.06);
          border: 2px solid transparent; }}
  .card.flagged {{ border-color: #28a745; }}
  .card img {{ display: block; width: 100%; height: auto; cursor: zoom-in; }}
  .card .label {{ padding: 8px 10px; font-size: 12px; line-height: 1.4; }}
  .card .h {{ font-weight: 600; }}
  .card .sub {{ opacity: 0.7; font-size: 11px; }}
  .card .ocr {{ padding: 6px 10px 10px; font-size: 11px; line-height: 1.35;
               border-top: 1px solid rgba(127,127,127,0.2); margin-top: 4px; }}
  .card .ocr pre {{ margin: 4px 0; white-space: pre-wrap; word-break: break-word;
                   font-family: ui-monospace, SF Mono, Menlo, monospace;
                   font-size: 10px; opacity: 0.8; max-height: 80px; overflow: auto; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px;
           background: #28a745; color: white; font-size: 10px; margin-right: 4px; }}
  .lightbox {{ position: fixed; inset: 0; background: rgba(0,0,0,0.9);
               display: none; align-items: center; justify-content: center;
               cursor: zoom-out; z-index: 100; }}
  .lightbox.on {{ display: flex; }}
  .lightbox img {{ max-width: 96vw; max-height: 96vh; object-fit: contain; }}
  .footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid rgba(127,127,127,0.3);
             font-size: 12px; opacity: 0.7; }}
</style>
</head>
<body>
  <h1>Parking sign report</h1>
  <div class="meta">
    <dl>
      <dt>Address asked</dt><dd>{address_q}</dd>
      <dt>Address resolved</dt><dd>{address}</dd>
      <dt>Coordinates</dt><dd>{lat:.6f}, {lng:.6f}</dd>
      <dt>Address pano</dt><dd>{pano_id} (date {pano_date})</dd>
      <dt>Total images</dt><dd>{n_total}</dd>
      <dt>Flagged as parking-like</dt><dd>{n_flagged} (OCR keyword score &ge; {flag_threshold})</dd>
      <dt>Open in Street View</dt>
      <dd><a href="{sv_link}" target="_blank" rel="noopener">View interactive Street View</a></dd>
    </dl>
  </div>

  {pano_blocks}

  <div class="footer">
    Click any image to enlarge. Images with a green border were flagged
    by Tesseract OCR as having parking-keyword text. Tesseract isn't
    perfect on Australian sign fonts &mdash; if a sign you can see by eye
    isn't flagged, that doesn't mean it isn't there.
  </div>
  <div class="lightbox" id="lb" onclick="this.classList.remove('on')"><img id="lb-img" alt=""></div>
<script>
  document.querySelectorAll('img').forEach(img => {{
    if (img.id === 'lb-img') return;
    img.addEventListener('click', () => {{
      const lb = document.getElementById('lb');
      document.getElementById('lb-img').src = img.src;
      lb.classList.add('on');
    }});
  }});
</script>
</body>
</html>
"""


def _img_card(img: CapturedImage, annotated_path: Optional[str] = None) -> str:
    rel = Path(img.file_path).name
    src = f"images/{escape(rel)}"
    if annotated_path:
        ann_rel = Path(annotated_path).name
        src = f"annotated/{escape(ann_rel)}"
    flagged = "flagged" if img.keyword_score >= PARKING_FLAG_SCORE else ""
    badge = ""
    if img.keyword_score >= PARKING_FLAG_SCORE:
        badge = '<span class="badge">PARKING</span>'
    keywords = ", ".join(img.keywords_found) if img.keywords_found else ""
    ocr_block = ""
    if img.ocr_text or keywords:
        ocr_block = (
            f'<div class="ocr">{badge}'
            f'<div class="sub">{escape(keywords) if keywords else "(no keywords)"}'
            f' &middot; score {img.keyword_score:.1f}</div>'
            f'<pre>{escape(img.ocr_text or "")}</pre>'
            f'</div>'
        )
    sub = (f"pitch {img.pitch:+.0f}&deg; &middot; fov {img.fov:.0f}&deg;")
    return (
        f'<div class="card {flagged}">'
        f'<img src="{src}" alt="" loading="lazy">'
        f'<div class="label">'
        f'<span class="h">heading {img.heading:.0f}&deg;</span> '
        f'<span class="sub">{sub}</span>'
        f'</div>'
        f'{ocr_block}'
        f'</div>'
    )


def build_html(report: CaptureReport, html_path: Path,
               annotated_paths: dict[str, str]) -> None:
    # Group images by pano (by pano_id), then by purpose, sorted by distance.
    by_pano: dict[str, list[CapturedImage]] = {}
    for img in report.images:
        by_pano.setdefault(img.pano_id, []).append(img)

    # Sort panos by distance ascending; address pano (distance 0) first.
    sorted_pano_ids = sorted(by_pano.keys(),
                             key=lambda pid: by_pano[pid][0].pano_distance_m)

    blocks = []
    for pid in sorted_pano_ids:
        imgs = by_pano[pid]
        first = imgs[0]
        flagged_in_pano = sum(1 for i in imgs if i.keyword_score >= PARKING_FLAG_SCORE)
        kind = ("address pano" if first.pano_distance_m < 1.0
                else f"{first.pano_distance_m:.1f}m away")
        cards = []
        for img in sorted(imgs, key=lambda x: (x.pitch, x.heading)):
            cards.append(_img_card(img, annotated_paths.get(img.file_path)))
        flagged_label = (f' <span class="sub">&middot; {flagged_in_pano} flagged</span>'
                         if flagged_in_pano else "")
        blocks.append(
            f'<div class="pano-block">'
            f'<div class="pano-header">'
            f'Pano {escape(pid[:14])}.. '
            f'<span class="sub">({kind} &middot; date {escape(first.pano_date or "?")} '
            f'&middot; {len(imgs)} images){flagged_label}</span>'
            f'</div>'
            f'<div class="grid">{"".join(cards)}</div>'
            f'</div>'
        )

    sv_link = (f"https://www.google.com/maps/@?api=1&map_action=pano"
               f"&viewpoint={report.lat},{report.lng}")
    n_flagged = sum(1 for i in report.images if i.keyword_score >= PARKING_FLAG_SCORE)

    html = HTML_TEMPLATE.format(
        address_q=escape(report.address_query),
        address=escape(report.resolved_address),
        lat=report.lat, lng=report.lng,
        pano_id=escape(report.pano_id or "?"),
        pano_date=escape(report.pano_date or "?"),
        n_total=len(report.images),
        n_flagged=n_flagged,
        flag_threshold=PARKING_FLAG_SCORE,
        sv_link=sv_link,
        pano_blocks="\n".join(blocks) if blocks else "<p>No images.</p>",
    )
    html_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration: run_parking_check() — used by both CLI main() and api.py
# ---------------------------------------------------------------------------

class ParkingCheckError(RuntimeError):
    """Raised by run_parking_check when capture cannot complete. The
    `code` attribute mirrors the CLI exit code (3 = no Street View
    nearby, 4 = no images could be captured)."""
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def run_parking_check(
    google_key: str,
    *,
    out_dir: Path,
    address: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 0.0,
    max_panos: Optional[int] = None,
    same_street: bool = True,
    headings_count: int = 8,
    pitches: Optional[list[float]] = None,
    fovs: Optional[list[int]] = None,
    size: str = "640x640",
    use_thumbnail: bool = False,
    thumbnail_size: tuple[int, int] = (1280, 720),
    do_ocr: bool = True,
    do_annotate: bool = True,
    zoom_specs: Optional[list[str]] = None,
    write_html: bool = True,
    focus: bool = False,
    fetch_workers: int = 8,
    ocr_workers: Optional[int] = None,
    image_quality: str = "fast",      # "fast" | "high"
    max_tile_upgrades: int = 3,
    tile_zoom: int = 4,
    log = print,
) -> tuple[CaptureReport, dict[str, str]]:
    """Run the full parking-check flow and return (report, annotated_paths).

    Either `address` or both (`lat`, `lng`) must be provided. If only
    coordinates are given, `resolved_address` will fall back to the
    formatted lat/lng.

    Returns:
      report: CaptureReport with all captured images + their OCR results.
      annotated_paths: dict mapping original image_path -> annotated path
        (only present when do_annotate=True and OCR found something).

    Raises:
      ParkingCheckError(code=3) if no Street View imagery is found.
      ParkingCheckError(code=4) if no images could be downloaded.
      ValueError on bad inputs.
    """
    pitches = pitches or [0.0]
    fovs = fovs or [80]
    zoom_specs = zoom_specs or []

    images_dir = out_dir / "images"
    annotated_dir = out_dir / "annotated"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotated_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Resolve coordinates ----
    addr_components: list = []
    if address:
        log(f"[1/4] Geocoding: {address!r}")
        lat_g, lng_g, formatted, addr_components = geocode(address, google_key)
        log(f"      -> {formatted}  ({lat_g:.6f}, {lng_g:.6f})")
        lat_resolved, lng_resolved = lat_g, lng_g
    elif lat is not None and lng is not None:
        log(f"[1/4] Using provided coordinates ({lat:.6f}, {lng:.6f})")
        lat_resolved, lng_resolved = lat, lng
        formatted = f"{lat:.6f}, {lng:.6f}"
        # If we'll filter by same-street, we need the address's components.
        if same_street and radius > 0:
            addr_components = reverse_geocode_components(lat_resolved, lng_resolved, google_key)
    else:
        raise ValueError("Must provide either `address` or both `lat` and `lng`.")

    # ---- 2. Pano discovery ----
    log(f"[2/4] Discovering Street View panos within {radius:.0f}m...")
    panos = discover_panos(lat_resolved, lng_resolved, radius, google_key)
    if not panos:
        raise ParkingCheckError(3, "No Street View imagery near this address/coordinate.")
    log(f"      found {len(panos)} distinct pano(s) before filtering")

    if same_street and radius > 0 and len(panos) > 1:
        log(f"      filtering by street name (--same-street)...")
        panos = filter_panos_same_street(panos, addr_components, google_key, log)

    address_pano = panos[0]
    # When the caller doesn't pin max_panos, scale it with the search
    # radius so wider radii actually scan more pano(s) instead of
    # collapsing to the same closest-10 set. Floor of 10 keeps small
    # radii on the original behaviour; ceil(radius/5) gives 20 panos at
    # radius=100m, 16 at 80m, etc. The schema caps this at 60 so
    # response time stays bounded even at the outer radius limit.
    effective_max_panos = max_panos
    if effective_max_panos is None:
        effective_max_panos = max(10, math.ceil(radius / 5)) if radius > 0 else 10
    other_panos = panos[1:1 + effective_max_panos]
    log(f"      using {1 + len(other_panos)} pano(s) "
        f"(address pano + {len(other_panos)} others, cap={effective_max_panos})")
    for p in [address_pano] + other_panos:
        log(f"        {p.pano_id[:14]}.. at {p.distance_m:.1f}m, date {p.date}")

    # ---- 3. Capture ----
    n_panos = 1 + len(other_panos)
    if use_thumbnail:
        per_pano = headings_count * len(pitches)
        log(f"[3/4] Capturing {headings_count} headings x {len(pitches)} pitch(es) "
            f"from {n_panos} pano(s) via THUMBNAIL endpoint at "
            f"{thumbnail_size[0]}x{thumbnail_size[1]} = {n_panos * per_pano} images...")
    else:
        log(f"[3/4] Capturing {headings_count} headings x {len(pitches)} pitch(es) "
            f"x {len(fovs)} fov(s) from {n_panos} pano(s) via Static API "
            f"= {n_panos * headings_count * len(pitches) * len(fovs)} images...")

    # ---- Build the full list of fetch tasks up front, then run them all
    # in parallel through one thread pool. This is much faster than
    # capturing pano-by-pano serially.
    if focus:
        # Address pano: 4 cardinal headings instead of `headings_count`.
        # (Risk: misses signs at NE/SE/SW/NW. Acceptable trade-off only
        # when speed matters more than recall.)
        addr_step = 90.0
        n_addr = 4
        addr_headings = [(i * addr_step) % 360.0 for i in range(n_addr)]
        # Each radius pano: 3 headings around the bearing-toward-address,
        # spaced 45° apart to match the normal sweep grid. So a sign that
        # would have shown up at e.g. heading=254 in unfocused mode also
        # shows up here.
        radius_offsets = [-45.0, 0.0, 45.0]
        log(f"      focus mode: {len(addr_headings)} headings on address pano, "
            f"{len(radius_offsets)} on each radius pano (±45°)")
    else:
        addr_step = 360.0 / headings_count
        addr_headings = [(i * addr_step) % 360.0 for i in range(headings_count)]
        radius_offsets = [(i * (360.0 / headings_count)) for i in range(headings_count)]

    fetch_tasks: list[_FetchTask] = []
    # Effective FOVs for thumbnail mode collapses to a single null FOV.
    effective_fovs = [0] if use_thumbnail else fovs

    def fname_for(prefix: str, h: float, p: float, fov: int, with_fov: bool) -> str:
        h_norm = h % 360.0
        if h_norm >= 359.995:
            h_norm = 0.0
        if with_fov:
            return (f"{prefix}_h{int(round(h_norm)):03d}"
                    f"_p{int(round(p)):+03d}_f{int(round(fov)):03d}.jpg")
        return (f"{prefix}_h{int(round(h_norm)):03d}"
                f"_p{int(round(p)):+03d}_thumb.jpg")

    # Address-pano tasks
    for h in addr_headings:
        h_norm = h % 360.0
        if h_norm >= 359.995:
            h_norm = 0.0
        for p in pitches:
            for fov in effective_fovs:
                fetch_tasks.append(_FetchTask(
                    pano=address_pano, heading=h_norm, pitch=p, fov=fov,
                    fname=fname_for("addr_pano", h_norm, p, fov, not use_thumbnail),
                    purpose="sweep",
                ))

    # Radius-pano tasks
    for p_pano in other_panos:
        bearing = bearing_deg(p_pano.lat, p_pano.lng, lat_resolved, lng_resolved)
        prefix = f"radius_{int(round(p_pano.distance_m)):03d}m_{p_pano.pano_id[:8]}"
        for off in radius_offsets:
            h = (bearing + off) % 360.0
            if h >= 359.995:
                h = 0.0
            for pp in pitches:
                for fov in effective_fovs:
                    fetch_tasks.append(_FetchTask(
                        pano=p_pano, heading=h, pitch=pp, fov=fov,
                        fname=fname_for(prefix, h, pp, fov, not use_thumbnail),
                        purpose="radius_scan",
                    ))

    log(f"      submitting {len(fetch_tasks)} captures via {fetch_workers} workers...")
    captures: list[CapturedImage] = _execute_fetch_tasks(
        fetch_tasks, size=size, key=google_key, images_dir=images_dir,
        use_thumbnail=use_thumbnail, thumbnail_size=thumbnail_size,
        max_workers=fetch_workers, log=log,
    )

    # Manual zooms (from the address pano).
    for i, spec in enumerate(zoom_specs, start=1):
        try:
            mz_h, mz_fov, mz_p = parse_zoom_spec(spec)
        except (ValueError, IndexError) as exc:
            log(f"      (bad zoom spec {spec!r}: {exc})")
            continue
        fname = f"manual_{i:02d}_h{int(round(mz_h)):03d}_p{int(round(mz_p)):+03d}.jpg"
        fpath = images_dir / fname
        if use_thumbnail:
            w, ht = thumbnail_size
            ok = fetch_streetview_thumbnail(
                pano_id=address_pano.pano_id, heading=mz_h, pitch=mz_p,
                width=w, height=ht, out_path=fpath,
            )
            mz_fov = 0
        else:
            ok = fetch_streetview_image(
                pano_id=address_pano.pano_id, heading=mz_h, pitch=mz_p,
                fov=mz_fov, size=size, key=google_key, out_path=fpath,
            )
        if ok:
            captures.append(CapturedImage(
                purpose="manual_zoom",
                pano_id=address_pano.pano_id,
                pano_date=address_pano.date,
                pano_distance_m=0.0,
                heading=mz_h, pitch=mz_p, fov=mz_fov,
                lat=address_pano.lat, lng=address_pano.lng,
                file_path=str(fpath),
            ))

    if not captures:
        raise ParkingCheckError(4, "No images could be captured.")

    # ---- 4. OCR + annotate ----
    annotated_paths: dict[str, str] = {}
    if do_ocr:
        log(f"[4/4] OCR + annotate ({len(captures)} images)...")
        flagged, annotated_paths = ocr_and_annotate_all(
            captures, annotated_dir, do_annotate=do_annotate, log=log,
            max_workers=ocr_workers,
        )
    else:
        flagged = 0
        log("[4/4] Skipping OCR")

    # ---- 5. (optional) High-res tile upgrade for flagged images ----
    if image_quality == "high" and do_ocr and flagged > 0:
        upgraded = upgrade_flagged_with_tiles(
            captures, annotated_paths, images_dir, annotated_dir,
            zoom=tile_zoom, max_upgrades=max_tile_upgrades, log=log,
        )
        log(f"      tile upgrade: {upgraded} image(s) replaced with high-res versions")

    report = CaptureReport(
        address_query=address or "",
        resolved_address=formatted,
        lat=lat_resolved, lng=lng_resolved,
        pano_id=address_pano.pano_id, pano_date=address_pano.date,
        images=captures,
        ocr_used=do_ocr,
    )

    # Persist machine-readable + HTML report
    (out_dir / "meta.json").write_text(json.dumps(asdict(report), indent=2))
    if write_html:
        build_html(report, out_dir / "index.html", annotated_paths)

    log(f"      done: {len(captures)} captured, {flagged} flagged")
    return report, annotated_paths


# ---------------------------------------------------------------------------
# Main (CLI)
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture Google Street View images around an address, "
                    "OCR every one, and build an HTML contact sheet "
                    "highlighting parking-sign-like text.")
    parser.add_argument("address", help="Street address to check")
    parser.add_argument("--out", default="./report",
                        help="Output directory (default: ./report)")
    parser.add_argument("--radius", type=float, default=0.0,
                        help="Scan all distinct panos within this many metres "
                             "of the address (default 0 = address only). "
                             "Try 30-50 for inner-city, up to 200 for sparse coverage.")
    parser.add_argument("--max-panos", type=int, default=10,
                        help="Cap on extra panos beyond the address pano "
                             "(sorted by distance, default 10).")
    parser.add_argument("--same-street", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Only keep panos that reverse-geocode to the SAME "
                             "street name as the address. Default ON (so "
                             "--radius 50 only walks the same street, not the "
                             "back lane or cross street). Disable with "
                             "--no-same-street to scan a full radius circle.")
    parser.add_argument("--headings", type=int, default=8,
                        help="Number of evenly-spaced headings to capture from "
                             "EVERY pano (default 8). At radius panos the sweep "
                             "starts pointing at the address.")
    parser.add_argument("--pitches", default="0",
                        help="Comma-separated pitch angles to capture at every "
                             "heading. Default '0' (eye level). Try '0,10,-5' "
                             "if signs are at varying heights / on hilly streets. "
                             "Each pitch multiplies the capture count.")
    parser.add_argument("--fovs", default="80",
                        help="Comma-separated FOV values to capture at every "
                             "(pano, heading, pitch). Default '80' (single "
                             "wide sweep). Try '80,30' for a wide overview "
                             "PLUS a sharp narrow zoom at every heading - "
                             "doubles the capture count but reads distant "
                             "signs much more reliably (the free-tier 640x640 "
                             "image at FOV=80 makes 30 m signs ~4 px wide; "
                             "at FOV=30 they're ~12 px).")
    parser.add_argument("--size", default="640x640",
                        help="Image size for the Static API (default 640x640, "
                             "free-tier max). Ignored when --use-thumbnail.")
    parser.add_argument("--use-thumbnail", action="store_true",
                        help="Fetch via the UNOFFICIAL "
                             "streetviewpixels-pa.googleapis.com/v1/thumbnail "
                             "endpoint instead of the Static API. "
                             "Pros: higher resolution (set with --thumbnail-size); "
                             "no API key needed for the captures; no per-image "
                             "cost. Cons: undocumented Google endpoint, can break; "
                             "no FOV control (--fovs is ignored); ToS gray area.")
    parser.add_argument("--thumbnail-size", default="1280x720",
                        help="Output WxH for thumbnail-endpoint captures "
                             "(default 1280x720). Used only when --use-thumbnail "
                             "is on. Try '1600x900' or '2048x1152' for sharper "
                             "captures (Google may serve a smaller image if it "
                             "doesn't have that resolution available).")
    parser.add_argument("--no-ocr", action="store_true",
                        help="Skip Tesseract OCR. Capture images only.")
    parser.add_argument("--no-annotate", action="store_true",
                        help="Skip drawing per-word boxes from Tesseract on "
                             "the contact-sheet images (visual aid only).")
    parser.add_argument("--zoom", action="append", default=[],
                        metavar="HEADING:FOV:PITCH",
                        help="Manual zoom capture, e.g. '--zoom 252:25:-5'. "
                             "Captured from the address pano. Repeatable.")
    parser.add_argument("--focus", action="store_true",
                        help="Focus mode: capture only the headings most likely "
                             "to see kerb-side parking signs. Address pano gets "
                             "4 cardinal headings (N/E/S/W); each radius pano "
                             "gets 3 headings (bearing-toward-address ±30°). "
                             "Roughly halves the capture count and OCR time.")
    parser.add_argument("--fetch-workers", type=int, default=8,
                        help="Concurrent threads for image fetching (default 8). "
                             "Higher values are faster but get rate-limited by "
                             "Google's thumbnail endpoint above ~12.")
    parser.add_argument("--ocr-workers", type=int, default=0,
                        help="Concurrent threads for Tesseract OCR (default 0 = "
                             "auto-detect = number of CPU cores).")
    args = parser.parse_args()

    google_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not google_key:
        print("ERROR: GOOGLE_MAPS_API_KEY is not set. See README.", file=sys.stderr)
        return 2

    if not args.no_ocr and not _DETECT_OK:
        print(f"WARNING: OCR module not available ({_DETECT_IMPORT_ERROR}). "
              "Falling back to capture-only mode.", file=sys.stderr)
        args.no_ocr = True

    out_dir = Path(args.out).expanduser().resolve()
    pitches = parse_pitch_list(args.pitches)
    fovs = parse_fov_list(args.fovs)
    thumbnail_size = parse_size(args.thumbnail_size) if args.use_thumbnail else (1280, 720)

    try:
        report, annotated_paths = run_parking_check(
            google_key,
            out_dir=out_dir,
            address=args.address,
            radius=args.radius,
            max_panos=args.max_panos,
            same_street=args.same_street,
            headings_count=args.headings,
            pitches=pitches,
            fovs=fovs,
            size=args.size,
            use_thumbnail=args.use_thumbnail,
            thumbnail_size=thumbnail_size,
            do_ocr=not args.no_ocr,
            do_annotate=not args.no_annotate,
            zoom_specs=args.zoom,
            write_html=True,
            focus=args.focus,
            fetch_workers=args.fetch_workers,
            ocr_workers=args.ocr_workers or None,
            log=print,
        )
    except ParkingCheckError as exc:
        print(f"      ERROR: {exc}", file=sys.stderr)
        return exc.code

    flagged = sum(1 for i in report.images if i.keyword_score >= PARKING_FLAG_SCORE)
    print()
    print(f"Done. {len(report.images)} image(s) captured.")
    if report.ocr_used:
        print(f"  Flagged as parking-like: {flagged} (keyword score >= {PARKING_FLAG_SCORE})")
    print(f"  Open in your browser:")
    print(f"    {out_dir / 'index.html'}")
    print(f"  Raw images : {out_dir / 'images'}")
    print(f"  Metadata   : {out_dir / 'meta.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
