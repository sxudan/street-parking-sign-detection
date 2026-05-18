"""
tile_probe.py
=============
Compare image quality between Google Street View's unofficial endpoints:

  1. /v1/thumbnail     - what we use today (1024x576 max)
  2. /v1/tile          - what Google Maps' interactive viewer uses
                         (high-resolution tile-stitched panoramas)

For a given pano_id + heading + pitch, the probe:
  - Fetches every tile in the panorama at the chosen zoom level (in parallel).
  - Stitches them into one equirectangular JPEG.
  - Crops a slice corresponding to the requested heading + FOV.
  - Fetches the same view via the thumbnail endpoint.
  - Saves both crops side by side so you can eyeball the difference.

Usage examples:

    # Validate on the South Yarra 2P sign (heading=33 from a 21m-away pano)
    python tile_probe.py bmcsjUdAEf564R-rKwBkIA --heading 33 --zoom 4

    # Lower zoom = fewer tiles but lower quality
    python tile_probe.py bmcsjUdAEf564R-rKwBkIA --heading 33 --zoom 3

    # The Commercial Rd 1P sign
    python tile_probe.py 83744MrNE3OnlhHH48Pjbw --heading 14 --zoom 4

The output folder ends up looking like:
    tile-probe/
        pano_bmcsjUdA_z4_full.jpg          (full ~8192x4096 panorama)
        pano_bmcsjUdA_z4_h033_crop.jpg     (high-res slice from tiles)
        pano_bmcsjUdA_thumb_h033.jpg       (the same view via thumbnail)

Both endpoints are unofficial Google Maps APIs. Same ToS gray-area as
the thumbnail endpoint we already use. Free.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests

try:
    from PIL import Image
except ImportError:
    print("ERROR: pillow is required. pip install pillow", file=sys.stderr)
    sys.exit(1)


TILE_URL = "https://streetviewpixels-pa.googleapis.com/v1/tile"
THUMBNAIL_URL = "https://streetviewpixels-pa.googleapis.com/v1/thumbnail"
TILE_SIZE = 512


# ---------------------------------------------------------------------------
# Tile grid math
# ---------------------------------------------------------------------------

def grid_size(zoom: int) -> tuple[int, int]:
    """Approximate (cols, rows) for a Street View pano at the given zoom.

    The actual grid varies a bit between panos, but the pattern observed
    on enough panos is:
        zoom 0: 1 x 1
        zoom 1: 2 x 1
        zoom 2: 4 x 2
        zoom 3: 8 x 4
        zoom 4: 16 x 8
        zoom 5: 32 x 16   (some panos are smaller; 404s on extra tiles
                           are tolerated below)
    """
    if zoom <= 0:
        return (1, 1)
    if zoom == 1:
        return (2, 1)
    return (2 ** zoom, 2 ** (zoom - 1))


def fetch_tile(pano_id: str, x: int, y: int, zoom: int,
               session: requests.Session) -> Optional[Image.Image]:
    """Fetch one tile. Returns None if the tile doesn't exist (404 / placeholder)."""
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
    if r.status_code != 200:
        return None
    if len(r.content) < 200:
        return None
    try:
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None
    return img


def fetch_full_pano(pano_id: str, zoom: int,
                    max_workers: int = 8, log=print) -> tuple[Image.Image, dict]:
    """Fetch every tile in the pano grid at `zoom` and stitch into one image.

    Returns the stitched panorama plus a stats dict (succeeded / 404'd / total).
    """
    cols, rows = grid_size(zoom)
    total = cols * rows
    log(f"  grid: {cols} x {rows} = {total} tiles, each {TILE_SIZE}x{TILE_SIZE}")
    log(f"  expected stitched size: {cols * TILE_SIZE} x {rows * TILE_SIZE}")

    canvas = Image.new("RGB", (cols * TILE_SIZE, rows * TILE_SIZE), (32, 32, 32))
    coords = [(x, y) for y in range(rows) for x in range(cols)]

    succeeded = 0
    missing = 0
    started = time.time()

    with requests.Session() as session, ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(fetch_tile, pano_id, x, y, zoom, session): (x, y) for x, y in coords
        }
        done = 0
        for f in as_completed(futures):
            x, y = futures[f]
            tile = f.result()
            done += 1
            if tile is None:
                missing += 1
            else:
                canvas.paste(tile, (x * TILE_SIZE, y * TILE_SIZE))
                succeeded += 1
            # Light progress indicator: every 8 tiles or last one
            if done % 8 == 0 or done == total:
                log(f"    {done}/{total} fetched ({succeeded} ok, {missing} missing)")

    elapsed = time.time() - started
    return canvas, {
        "cols": cols, "rows": rows, "total": total,
        "succeeded": succeeded, "missing": missing,
        "elapsed_s": round(elapsed, 2),
    }


def crop_heading_slice(pano: Image.Image, heading: float, pitch: float,
                       fov_h: float = 80.0, fov_v: float = 50.0) -> Image.Image:
    """Crop an equirectangular FOV-sized slice from the full panorama.

    Heading 0° is assumed to align with column 0 of the pano. The pano
    is 360° wide; wraparound across the seam is handled by stitching
    a left-edge piece + right-edge piece if needed.
    """
    w, h = pano.size
    cx = (heading / 360.0) * w
    cy = ((90.0 - pitch) / 180.0) * h

    crop_w = (fov_h / 360.0) * w
    crop_h = (fov_v / 180.0) * h

    x1f = cx - crop_w / 2
    y1f = cy - crop_h / 2
    x2f = cx + crop_w / 2
    y2f = cy + crop_h / 2

    # Vertical clipping: panos are 180° tall, simply clamp.
    y1 = max(0, int(round(y1f)))
    y2 = min(h, int(round(y2f)))

    # Horizontal: handle wraparound across the seam.
    if x1f < 0:
        left = pano.crop((int(round(w + x1f)), y1, w, y2))
        right = pano.crop((0, y1, int(round(x2f)), y2))
        out = Image.new("RGB", (left.width + right.width, left.height))
        out.paste(left, (0, 0))
        out.paste(right, (left.width, 0))
        return out
    if x2f > w:
        left = pano.crop((int(round(x1f)), y1, w, y2))
        right = pano.crop((0, y1, int(round(x2f - w)), y2))
        out = Image.new("RGB", (left.width + right.width, left.height))
        out.paste(left, (0, 0))
        out.paste(right, (left.width, 0))
        return out
    return pano.crop((int(round(x1f)), y1, int(round(x2f)), y2))


# ---------------------------------------------------------------------------
# Thumbnail fetch (for side-by-side comparison)
# ---------------------------------------------------------------------------

def fetch_thumbnail(pano_id: str, heading: float, pitch: float,
                    width: int, height: int) -> Optional[Image.Image]:
    """Fetch one thumbnail at the requested heading/pitch."""
    params = {
        "output": "thumbnail",
        "cb_client": "maps_sv.tactile.gps",
        "panoid": pano_id,
        "w": str(width),
        "h": str(height),
        "thumb": "3",
        "yaw": f"{heading:.4f}",
        "pitch": f"{pitch:.4f}",
    }
    try:
        r = requests.get(THUMBNAIL_URL, params=params, timeout=30)
    except requests.RequestException as e:
        print(f"  thumbnail fetch failed: {e}")
        return None
    if r.status_code != 200 or len(r.content) < 3000:
        return None
    return Image.open(io.BytesIO(r.content)).convert("RGB")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Probe Street View tile endpoint quality.")
    p.add_argument("pano_id", help="Street View pano ID, e.g. 'bmcsjUdAEf564R-rKwBkIA'")
    p.add_argument("--zoom", type=int, default=4, choices=[2, 3, 4, 5],
                   help="Tile zoom level. Higher = sharper but more tiles. Default 4 (16x8 = 128 tiles).")
    p.add_argument("--heading", type=float, default=0.0,
                   help="Camera heading in degrees (0=north, 90=east, 180=south, 270=west).")
    p.add_argument("--pitch", type=float, default=0.0,
                   help="Camera pitch in degrees (negative = looking down, positive = looking up).")
    p.add_argument("--fov-h", type=float, default=80.0, help="Horizontal FOV for the crop (default 80).")
    p.add_argument("--fov-v", type=float, default=50.0, help="Vertical FOV for the crop (default 50).")
    p.add_argument("--thumb-size", default="1600x900",
                   help="Thumbnail WxH for the comparison image (default 1600x900).")
    p.add_argument("--workers", type=int, default=8, help="Parallel tile fetches (default 8).")
    p.add_argument("--out", default="./tile-probe", help="Output directory.")
    p.add_argument("--save-full-pano", action="store_true",
                   help="Also save the full stitched equirectangular panorama (large file).")
    args = p.parse_args()

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    short_id = args.pano_id[:8]
    print(f"=== Tile probe ===")
    print(f"pano_id  : {args.pano_id}")
    print(f"zoom     : {args.zoom}")
    print(f"heading  : {args.heading}°  pitch: {args.pitch}°  fov: {args.fov_h}°x{args.fov_v}°")
    print(f"out      : {out_dir}")
    print()

    # --- 1. Stitch full pano via tiles ---
    print(f"[1/3] Fetching tiles at zoom {args.zoom}...")
    pano, stats = fetch_full_pano(args.pano_id, args.zoom, max_workers=args.workers, log=print)
    print(f"      done in {stats['elapsed_s']}s "
          f"({stats['succeeded']}/{stats['total']} ok, {stats['missing']} missing)")
    print()

    if args.save_full_pano:
        full_path = out_dir / f"pano_{short_id}_z{args.zoom}_full.jpg"
        pano.save(full_path, "JPEG", quality=85)
        print(f"      saved full pano: {full_path.name} "
              f"({full_path.stat().st_size // 1024}KB, {pano.size[0]}x{pano.size[1]})")

    # --- 2. Crop the heading slice from the stitched pano ---
    print(f"[2/3] Cropping FOV slice from stitched pano...")
    crop = crop_heading_slice(pano, args.heading, args.pitch, args.fov_h, args.fov_v)
    crop_path = out_dir / f"pano_{short_id}_z{args.zoom}_h{int(round(args.heading)):03d}_crop.jpg"
    crop.save(crop_path, "JPEG", quality=88)
    print(f"      saved {crop_path.name} "
          f"({crop_path.stat().st_size // 1024}KB, {crop.size[0]}x{crop.size[1]})")
    print()

    # --- 3. Fetch the equivalent thumbnail ---
    print(f"[3/3] Fetching thumbnail at the same heading...")
    w, h = (int(v) for v in args.thumb_size.lower().split("x"))
    started = time.time()
    thumb = fetch_thumbnail(args.pano_id, args.heading, args.pitch, w, h)
    thumb_elapsed = time.time() - started
    if thumb is None:
        print(f"      thumbnail unavailable")
        thumb_size = (0, 0)
        thumb_kb = 0
    else:
        thumb_path = out_dir / f"pano_{short_id}_thumb_h{int(round(args.heading)):03d}.jpg"
        thumb.save(thumb_path, "JPEG", quality=88)
        thumb_size = thumb.size
        thumb_kb = thumb_path.stat().st_size // 1024
        print(f"      saved {thumb_path.name} "
              f"({thumb_kb}KB, {thumb_size[0]}x{thumb_size[1]}) in {thumb_elapsed:.1f}s")
    print()

    # --- Summary ---
    print("=" * 60)
    print("SUMMARY — eyeball the two crops in the output folder.")
    print("=" * 60)
    print(f"Tile crop  : {crop.size[0]}x{crop.size[1]}")
    print(f"Thumbnail  : {thumb_size[0]}x{thumb_size[1]}")
    if thumb_size[0] and thumb_size[1]:
        ratio = (crop.size[0] * crop.size[1]) / (thumb_size[0] * thumb_size[1])
        print(f"Pixel ratio: tiles are {ratio:.1f}x more pixels than thumbnail")
    print(f"Tile time  : {stats['elapsed_s']}s ({stats['total']} tiles, {args.workers} workers)")
    print(f"Thumb time : {thumb_elapsed:.1f}s")
    print()
    print(f"Open both files and compare readability of distant signs:")
    print(f"  thumbnail: {thumb_path.name if thumb else '(missing)'}")
    print(f"  tile crop: {crop_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
