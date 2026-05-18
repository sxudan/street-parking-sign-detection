"""
tile_fetcher.py
===============
Production tile fetcher for the unofficial Google Street View
streetviewpixels-pa.googleapis.com/v1/tile endpoint.

Public surface:
    fetch_tile_crop(pano_id, heading, pitch, *,
                    fov_h=80, fov_v=50, zoom=4, out_path=...,
                    max_workers=4, retries=3, log=...)
        -> (PIL.Image, stats: dict)

Strategy:
  1. From (heading, pitch, fov_h, fov_v, zoom), compute the minimum
     bounding box of tiles in the panorama grid that contains the FOV.
  2. Fetch only those tiles in parallel (default 4 workers, with
     retry+backoff for transient 429/5xx).
  3. Stitch onto a local canvas. Wraparound across heading=0/360 is
     handled by addressing tiles modulo `cols` while keeping the
     local canvas contiguous.
  4. Crop the canvas to the exact FOV pixel rectangle around the
     requested heading + pitch.
  5. Optionally save the cropped JPEG to disk.

Same trade-offs as the thumbnail endpoint:
  - UNDOCUMENTED Google internal endpoint. Can change without notice.
  - ToS gray area for high-volume / commercial use.
  - Free; no API key required for the request itself.
"""
from __future__ import annotations

import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

try:
    from PIL import Image
except ImportError as exc:
    raise RuntimeError(
        "tile_fetcher requires Pillow. pip install pillow"
    ) from exc


TILE_URL = "https://streetviewpixels-pa.googleapis.com/v1/tile"
TILE_SIZE = 512


# ---------------------------------------------------------------------------
# Grid geometry
# ---------------------------------------------------------------------------

def grid_size(zoom: int) -> tuple[int, int]:
    """Approximate (cols, rows) for a Street View pano at this zoom level."""
    if zoom <= 0:
        return (1, 1)
    if zoom == 1:
        return (2, 1)
    return (2 ** zoom, 2 ** (zoom - 1))


@dataclass
class TileRange:
    """Describes the minimal tile rectangle needed to render a FOV crop.

    Columns are stored as *unwrapped* indices — they may be negative or
    >= cols. Use `% cols` to get the actual index for fetching.
    """
    start_col: int           # unwrapped, may be negative
    end_col: int             # exclusive, may be > cols
    start_row: int
    end_row: int             # exclusive
    cols: int                # full pano grid width
    rows: int                # full pano grid height
    pano_w_px: int           # full pano pixel width
    pano_h_px: int           # full pano pixel height

    @property
    def n_cols(self) -> int:
        return self.end_col - self.start_col

    @property
    def n_rows(self) -> int:
        return self.end_row - self.start_row

    @property
    def n_tiles(self) -> int:
        return self.n_cols * self.n_rows


def compute_tile_range(heading: float, pitch: float,
                       fov_h: float, fov_v: float,
                       zoom: int, padding: int = 0) -> TileRange:
    """Compute the smallest tile rectangle covering the requested FOV.

    `padding` adds N extra tiles on every side. Default 0 because the
    int math is already precise (start = floor(start_pixel/TILE_SIZE),
    end = floor(end_pixel/TILE_SIZE) + 1 covers every pixel in the FOV
    exactly). Bump to 1 if you ever see edge artefacts.
    """
    cols, rows = grid_size(zoom)
    pano_w = cols * TILE_SIZE
    pano_h = rows * TILE_SIZE

    # Centre of the crop in pano pixel coords.
    cx_pano = (heading / 360.0) * pano_w
    cy_pano = ((90.0 - pitch) / 180.0) * pano_h

    crop_w = (fov_h / 360.0) * pano_w
    crop_h = (fov_v / 180.0) * pano_h

    start_col_f = (cx_pano - crop_w / 2.0) / TILE_SIZE
    end_col_f = (cx_pano + crop_w / 2.0) / TILE_SIZE
    start_row_f = (cy_pano - crop_h / 2.0) / TILE_SIZE
    end_row_f = (cy_pano + crop_h / 2.0) / TILE_SIZE

    return TileRange(
        start_col=int(start_col_f) - padding,
        end_col=int(end_col_f) + padding + 1,
        start_row=max(0, int(start_row_f) - padding),
        end_row=min(rows, int(end_row_f) + padding + 1),
        cols=cols,
        rows=rows,
        pano_w_px=pano_w,
        pano_h_px=pano_h,
    )


# ---------------------------------------------------------------------------
# Tile HTTP fetch
# ---------------------------------------------------------------------------

def _fetch_tile(session: requests.Session, pano_id: str,
                x: int, y: int, zoom: int) -> Optional[Image.Image]:
    """Single tile GET. Returns None on any failure."""
    params = {
        "cb_client": "maps_sv.tactile",
        "panoid": pano_id,
        "x": x,
        "y": y,
        "zoom": zoom,
        "nbt": 1,
        "fover": 2,
    }
    try:
        r = session.get(TILE_URL, params=params, timeout=20)
    except requests.RequestException:
        return None
    if r.status_code != 200 or len(r.content) < 200:
        return None
    try:
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def _fetch_tile_with_retry(session: requests.Session, pano_id: str,
                           x: int, y: int, zoom: int,
                           retries: int = 3) -> Optional[Image.Image]:
    """Fetch a tile with exponential backoff on transient failures.

    Backoff schedule: ~0.4s, 0.8s, 1.6s. Total worst-case ~3s for one
    tile that just won't load.
    """
    for attempt in range(retries + 1):
        tile = _fetch_tile(session, pano_id, x, y, zoom)
        if tile is not None:
            return tile
        if attempt < retries:
            time.sleep(0.4 * (2 ** attempt))
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_tile_crop(
    pano_id: str,
    heading: float,
    pitch: float,
    *,
    fov_h: float = 80.0,
    fov_v: float = 50.0,
    zoom: int = 4,
    out_path: Optional[Path] = None,
    max_workers: int = 4,
    retries: int = 3,
    log: Callable[..., None] = lambda *_: None,
) -> tuple[Optional[Image.Image], dict]:
    """Fetch + stitch + crop a high-resolution Street View slice.

    Returns:
      (image, stats). `image` is a PIL.Image of the cropped FOV, or
      None if every tile fetch failed (extremely rare). `stats` reports
      what happened during the fetch.
    """
    started = time.time()
    tr = compute_tile_range(heading, pitch, fov_h, fov_v, zoom)

    # Local canvas in tile coords [0, n_cols) x [0, n_rows).
    canvas = Image.new(
        "RGB",
        (tr.n_cols * TILE_SIZE, tr.n_rows * TILE_SIZE),
        (32, 32, 32),
    )

    # Tasks: every (x_local, y_local) in the rectangle, mapped to a
    # wrapped fetch coordinate.
    tasks: list[tuple[int, int, int, int]] = []
    for x_local in range(tr.n_cols):
        x_unwrapped = tr.start_col + x_local
        x_wrapped = x_unwrapped % tr.cols
        for y_local in range(tr.n_rows):
            y = tr.start_row + y_local
            tasks.append((x_local, y_local, x_wrapped, y))

    succeeded = 0
    with requests.Session() as session, ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_fetch_tile_with_retry, session, pano_id, x_w, y, zoom, retries):
                (x_l, y_l) for x_l, y_l, x_w, y in tasks
        }
        for fut in as_completed(futures):
            x_l, y_l = futures[fut]
            tile = fut.result()
            if tile is not None:
                canvas.paste(tile, (x_l * TILE_SIZE, y_l * TILE_SIZE))
                succeeded += 1

    fetch_elapsed = time.time() - started

    # Crop the FOV pixel rectangle out of the local canvas.
    cx_pano = (heading / 360.0) * tr.pano_w_px
    cy_pano = ((90.0 - pitch) / 180.0) * tr.pano_h_px

    cx_local = cx_pano - tr.start_col * TILE_SIZE
    cy_local = cy_pano - tr.start_row * TILE_SIZE

    crop_w = (fov_h / 360.0) * tr.pano_w_px
    crop_h = (fov_v / 180.0) * tr.pano_h_px

    x1 = max(0, int(round(cx_local - crop_w / 2)))
    y1 = max(0, int(round(cy_local - crop_h / 2)))
    x2 = min(canvas.width, int(round(cx_local + crop_w / 2)))
    y2 = min(canvas.height, int(round(cy_local + crop_h / 2)))

    if x2 <= x1 or y2 <= y1:
        log(f"  ERROR computing crop region: ({x1},{y1})->({x2},{y2})")
        return None, {
            "tiles_total": tr.n_tiles, "tiles_fetched": succeeded,
            "fetch_seconds": round(fetch_elapsed, 2),
            "error": "crop region empty",
        }

    cropped = canvas.crop((x1, y1, x2, y2))

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out_path, "JPEG", quality=88)

    log(f"  tiles {succeeded}/{tr.n_tiles} in {fetch_elapsed:.2f}s "
        f"-> crop {cropped.size[0]}x{cropped.size[1]}")

    return cropped, {
        "tiles_total": tr.n_tiles,
        "tiles_fetched": succeeded,
        "fetch_seconds": round(fetch_elapsed, 2),
        "crop_w_px": cropped.size[0],
        "crop_h_px": cropped.size[1],
    }
