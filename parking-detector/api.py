"""
api.py - FastAPI wrapper around parking_check.run_parking_check()
=================================================================

Exposes a single endpoint that:
  - takes an address OR (lat, lng)
  - runs the full discover → capture → OCR pipeline
  - deletes every captured image that didn't flag as parking-relevant
  - groups the surviving images by pano
  - returns a JSON list of [{coordinate, pano, distance_m, images}]
  - serves the surviving images at /images/{job_id}/...

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Required env vars:
    GOOGLE_MAPS_API_KEY          - same key the CLI uses
    PARKING_RESULTS_DIR (opt)    - where job dirs live; defaults to ./api_results

Security: this endpoint runs paid Google Maps calls. Don't expose it
to the public internet without auth + rate limits.
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

import parking_check as pc
import detect_signs


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

RESULTS_ROOT = Path(os.environ.get(
    "PARKING_RESULTS_DIR", "./api_results"
)).expanduser().resolve()
RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Parking Sign Detector API",
    description=(
        "Given an address or coordinate, walks Google Street View around it "
        "and returns the parking signs visible nearby. Uses the unofficial "
        "thumbnail endpoint for image capture (free) and Tesseract for OCR. "
        "Images that don't flag as parking-relevant are deleted after the "
        "request completes."
    ),
    version="0.1.0",
)

# Serve surviving images at /images/<job_id>/<filename>
app.mount("/images", StaticFiles(directory=str(RESULTS_ROOT)), name="images")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ParkingRequest(BaseModel):
    address: Optional[str] = Field(
        default=None,
        description='Street address. Required if lat/lng not provided.',
        examples=["Unit 1/4-8 Osborne St, South Yarra VIC 3141"],
    )
    lat: Optional[float] = Field(default=None, description="Latitude (alternative to address).")
    lng: Optional[float] = Field(default=None, description="Longitude (alternative to address).")
    radius: float = Field(
        default=50,
        ge=0, le=300,
        description="Metres around the address to scan. 0 = address pano only.",
    )
    headings: int = Field(default=8, ge=1, le=36, description="Headings per pano.")
    pitches: str = Field(default="0", description="Comma-separated pitch angles (e.g. '0,-5').")
    thumbnail_size: str = Field(default="1600x900", description="Thumbnail WxH (e.g. '1600x900').")
    same_street: bool = Field(
        default=True,
        description="Only keep panos on the same street as the address.",
    )
    max_panos: int = Field(default=10, ge=1, le=30, description="Cap on extra panos beyond the address.")

    @model_validator(mode="after")
    def _check_input(self):
        if not self.address and (self.lat is None or self.lng is None):
            raise ValueError("Provide either `address` or both `lat` and `lng`.")
        return self


class SignImage(BaseModel):
    heading: float = Field(description="Compass heading the camera was facing (0-360).")
    pitch: float = Field(description="Camera pitch in degrees.")
    url: str = Field(description="URL to fetch the captured image (relative to API host).")
    annotated_url: Optional[str] = Field(
        default=None,
        description="URL to the annotated copy with green boxes around recognised text.",
    )
    ocr_text: str = Field(description="What Tesseract read above the confidence floor.")
    keywords_found: List[str] = Field(description="Parking keywords that scored points.")
    keyword_score: float = Field(description="Total parking-keyword score for this image.")


class ParkingLocation(BaseModel):
    coordinate: Dict[str, float] = Field(
        description='Pano location as {"lat": ..., "lng": ...}.'
    )
    pano_id: str = Field(description="Google Street View pano ID.")
    pano_date: Optional[str] = Field(description="When this pano was captured (YYYY-MM).")
    distance_m: float = Field(description="Distance from the queried address, in metres.")
    images: List[SignImage] = Field(
        description="Captured images from this pano that flagged as parking-relevant.",
    )


class ParkingResponse(BaseModel):
    address_query: Optional[str]
    resolved_address: str
    coordinate: Dict[str, float]
    parking_locations: List[ParkingLocation]
    stats: Dict[str, int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_unflagged_images(report: pc.CaptureReport,
                              annotated_paths: Dict[str, str]) -> int:
    """Delete every captured image (and its annotated copy) that didn't
    flag. Returns count of images that survived."""
    flagged_paths = {
        i.file_path for i in report.images
        if i.keyword_score >= detect_signs.PARKING_FLAG_SCORE
    }
    removed = 0
    for img in report.images:
        if img.file_path in flagged_paths:
            continue
        # Delete the raw capture
        try:
            Path(img.file_path).unlink(missing_ok=True)
            removed += 1
        except Exception:
            pass
        # And its annotated copy if any
        ann = annotated_paths.get(img.file_path)
        if ann:
            try:
                Path(ann).unlink(missing_ok=True)
            except Exception:
                pass
    return len(flagged_paths)


def _resolve_base_url(request: Request) -> str:
    """Determine the public base URL the client used to reach us.

    Order of precedence:
      1. PUBLIC_BASE_URL env var if set (override for proxy deployments).
      2. request.base_url, which respects X-Forwarded-{Proto,Host} headers
         when uvicorn is started with --proxy-headers.
    """
    override = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if override:
        return override
    return str(request.base_url).rstrip("/")


def _build_response(report: pc.CaptureReport,
                    annotated_paths: Dict[str, str],
                    job_dir: Path,
                    request: ParkingRequest,
                    base_url: str) -> ParkingResponse:
    # Group flagged images by pano
    by_pano: dict[str, List[pc.CapturedImage]] = {}
    for img in report.images:
        if img.keyword_score < detect_signs.PARKING_FLAG_SCORE:
            continue
        by_pano.setdefault(img.pano_id, []).append(img)

    # Build location entries sorted by distance ascending (closest first)
    locations: List[ParkingLocation] = []
    sorted_pids = sorted(by_pano.keys(),
                         key=lambda pid: by_pano[pid][0].pano_distance_m)
    for pid in sorted_pids:
        imgs = sorted(by_pano[pid], key=lambda i: i.heading)
        first = imgs[0]
        sign_images = []
        for i in imgs:
            raw_rel = Path(i.file_path).relative_to(RESULTS_ROOT).as_posix()
            ann_path = annotated_paths.get(i.file_path)
            ann_rel = (Path(ann_path).relative_to(RESULTS_ROOT).as_posix()
                       if ann_path and Path(ann_path).exists() else None)
            sign_images.append(SignImage(
                heading=i.heading,
                pitch=i.pitch,
                url=f"{base_url}/images/{raw_rel}",
                annotated_url=(f"{base_url}/images/{ann_rel}" if ann_rel else None),
                ocr_text=i.ocr_text,
                keywords_found=i.keywords_found,
                keyword_score=i.keyword_score,
            ))
        locations.append(ParkingLocation(
            coordinate={"lat": first.lat, "lng": first.lng},
            pano_id=pid,
            pano_date=first.pano_date,
            distance_m=round(first.pano_distance_m, 2),
            images=sign_images,
        ))

    images_kept = sum(len(loc.images) for loc in locations)
    return ParkingResponse(
        address_query=request.address,
        resolved_address=report.resolved_address,
        coordinate={"lat": report.lat, "lng": report.lng},
        parking_locations=locations,
        stats={
            "panos_with_signs": len(locations),
            "images_captured": len(report.images),
            "images_kept": images_kept,
            "images_deleted": len(report.images) - images_kept,
        },
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Quick readiness check. Confirms env + tesseract availability."""
    return {
        "status": "ok",
        "google_key_present": bool(os.environ.get("GOOGLE_MAPS_API_KEY")),
        "tesseract_available": pc._DETECT_OK,
        "results_dir": str(RESULTS_ROOT),
    }


@app.post("/parking-signs", response_model=ParkingResponse)
def find_parking_signs(req: ParkingRequest, request: Request) -> ParkingResponse:
    """Walk Street View around the address/coord, return images that flagged
    as containing parking signs. Non-flagged images are deleted from disk
    before the response is returned.

    The `url` and `annotated_url` fields in the response are absolute
    URLs (e.g. "http://localhost:8000/images/...") so consumers can
    fetch them directly without joining a base path.
    """
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not google_key:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_MAPS_API_KEY environment variable is not set.",
        )

    job_id = uuid.uuid4().hex[:12]
    job_dir = RESULTS_ROOT / job_id

    # Buffered log so we can attach diagnostics on error.
    log_lines: list[str] = []
    def log(*args):
        log_lines.append(" ".join(str(a) for a in args))

    try:
        thumbnail_size = pc.parse_size(req.thumbnail_size)
        pitches = pc.parse_pitch_list(req.pitches)

        report, annotated_paths = pc.run_parking_check(
            google_key,
            out_dir=job_dir,
            address=req.address,
            lat=req.lat, lng=req.lng,
            radius=req.radius,
            max_panos=req.max_panos,
            same_street=req.same_street,
            headings_count=req.headings,
            pitches=pitches,
            fovs=[80],                # ignored anyway when use_thumbnail
            use_thumbnail=True,       # always use the free endpoint
            thumbnail_size=thumbnail_size,
            do_ocr=True,
            do_annotate=True,
            write_html=False,         # no need for the HTML report in API mode
            log=log,
        )

        _cleanup_unflagged_images(report, annotated_paths)
        # Also drop the meta.json from disk - we don't need it after the response.
        meta_file = job_dir / "meta.json"
        if meta_file.exists():
            meta_file.unlink()

        base_url = _resolve_base_url(request)
        response = _build_response(report, annotated_paths, job_dir, req, base_url)

        # If nothing flagged at all, the job dir is now full of empty
        # subdirs - clean them up too.
        if response.stats["images_kept"] == 0:
            shutil.rmtree(job_dir, ignore_errors=True)

        return response

    except pc.ParkingCheckError as exc:
        # Tidy up: nothing useful was kept.
        shutil.rmtree(job_dir, ignore_errors=True)
        if exc.code == 3:
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"capture failed: {exc}\nlog tail: {log_lines[-10:]}",
        )


@app.get("/parking-signs", response_model=ParkingResponse)
def find_parking_signs_get(
    request: Request,
    address: Optional[str] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
    radius: float = Query(default=50, ge=0, le=300),
    headings: int = Query(default=8, ge=1, le=36),
    pitches: str = Query(default="0"),
    thumbnail_size: str = Query(default="1600x900"),
    same_street: bool = Query(default=True),
    max_panos: int = Query(default=10, ge=1, le=30),
) -> ParkingResponse:
    """Same as POST /parking-signs but as a GET so you can hit it from a
    browser."""
    return find_parking_signs(ParkingRequest(
        address=address, lat=lat, lng=lng,
        radius=radius, headings=headings, pitches=pitches,
        thumbnail_size=thumbnail_size, same_street=same_street,
        max_panos=max_panos,
    ), request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
