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

import requests
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
    max_panos: Optional[int] = Field(
        default=None, ge=1, le=60,
        description=(
            "Cap on extra panos beyond the address pano. When omitted (default), "
            "scales automatically with radius — roughly ceil(radius/5) with a floor "
            "of 10 — so wider radii actually scan more panos. Pin it explicitly to "
            "trade off between coverage and response time."
        ),
    )
    focus: bool = Field(
        default=False,
        description=(
            "Focus mode: capture only headings likely to see kerb-side "
            "parking signs (4 cardinal directions on address pano, "
            "bearing-±45° on radius panos = 3 captures around the kerb "
            "facing the address). Cuts captures and OCR by ~50% but "
            "CAN MISS SIGNS that sit at unexpected angles (corner "
            "properties, set-back buildings, opposite-kerb signs). "
            "Default off; enable when you want speed and accept some "
            "false negatives."
        ),
    )
    fetch_workers: int = Field(
        default=8, ge=1, le=16,
        description="Concurrent HTTP fetches for image captures (default 8).",
    )
    ocr_workers: int = Field(
        default=0, ge=0, le=32,
        description="Concurrent Tesseract OCR workers (0 = auto = num CPU cores).",
    )
    image_quality: str = Field(
        default="fast",
        description=(
            "'fast' (default): thumbnail-only captures, ~12-15s response, 1024x576 images. "
            "'high': thumbnail sweep + tile-stitched high-res upgrade for any image that "
            "flagged as a parking sign (~3.5x more pixels per glyph, OCR confidence ~2x). "
            "Adds ~3-5s when there are flagged signs to upgrade; same speed as 'fast' "
            "when nothing flags."
        ),
    )
    max_tile_upgrades: int = Field(
        default=3, ge=1, le=10,
        description="Cap on flagged images promoted to tile-stitched high-res in 'high' mode.",
    )

    @model_validator(mode="after")
    def _check_input(self):
        if not self.address and (self.lat is None or self.lng is None):
            raise ValueError("Provide either `address` or both `lat` and `lng`.")
        return self


class SignImage(BaseModel):
    heading: float = Field(description="Compass heading the camera was facing (0-360).")
    pitch: float = Field(description="Camera pitch in degrees.")
    url: str = Field(description="Absolute URL to fetch the captured image.")
    annotated_url: Optional[str] = Field(
        default=None,
        description="Absolute URL to the annotated copy with green boxes around recognised text.",
    )
    ocr_text: str = Field(description="What Tesseract read above the confidence floor.")
    keywords_found: List[str] = Field(description="Parking keywords that scored points.")
    keyword_score: float = Field(description="Total parking-keyword score for this image.")
    flagged: bool = Field(
        default=False,
        description=(
            "True if this image's OCR text scored at or above the parking-sign "
            "threshold (PARKING_FLAG_SCORE = 3.0). Always true for entries "
            "inside `parking_locations`. May be true or false inside "
            "`address_pano_preview`."
        ),
    )


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
    address_pano_preview: Optional[ParkingLocation] = Field(
        default=None,
        description=(
            "Always-included preview of the Street View pano nearest to the "
            "requested address. Contains EVERY captured heading/pitch from "
            "that pano, regardless of whether the image flagged as a parking "
            "sign. Useful when you want to show the user 'here's what this "
            "location looks like in Street View' even if no signs were found. "
            "Inspect each image's `flagged` field to filter for parking-sign "
            "matches. None when no Street View imagery was found at the "
            "queried coordinate."
        ),
    )
    parking_locations: List[ParkingLocation] = Field(
        description=(
            "Panos (address pano + nearby radius panos) where AT LEAST ONE "
            "image flagged as a parking sign. Each image inside has "
            "`flagged: true`. May be empty if nothing flagged."
        ),
    )
    stats: Dict[str, int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_unflagged_images(report: pc.CaptureReport,
                              annotated_paths: Dict[str, str]) -> Dict[str, int]:
    """Delete captured images that aren't worth keeping. Returns a stats dict.

    Keep:
      - Any image with keyword_score >= PARKING_FLAG_SCORE (flagged sign).
      - All images from the address pano (purpose='sweep'), regardless of
        flag status, so consumers always have a Street View preview of the
        requested coordinate.

    Delete everything else (radius_scan / manual_zoom that didn't flag).
    """
    flagged_paths = {
        i.file_path for i in report.images
        if i.keyword_score >= detect_signs.PARKING_FLAG_SCORE
    }
    address_pano_paths = {
        i.file_path for i in report.images if i.purpose == "sweep"
    }
    keep_paths = flagged_paths | address_pano_paths

    deleted = 0
    for img in report.images:
        if img.file_path in keep_paths:
            continue
        try:
            Path(img.file_path).unlink(missing_ok=True)
            deleted += 1
        except Exception:
            pass
        ann = annotated_paths.get(img.file_path)
        if ann:
            try:
                Path(ann).unlink(missing_ok=True)
            except Exception:
                pass

    return {
        "kept": len(keep_paths),
        "deleted": deleted,
        "flagged": len(flagged_paths),
        "address_preview": len(address_pano_paths),
    }


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


def _build_sign_image(img: pc.CapturedImage,
                      annotated_paths: Dict[str, str],
                      base_url: str) -> SignImage:
    """Build the URL-bearing SignImage record for a single CapturedImage."""
    raw_rel = Path(img.file_path).relative_to(RESULTS_ROOT).as_posix()
    ann_path = annotated_paths.get(img.file_path)
    ann_rel = (Path(ann_path).relative_to(RESULTS_ROOT).as_posix()
               if ann_path and Path(ann_path).exists() else None)
    return SignImage(
        heading=img.heading,
        pitch=img.pitch,
        url=f"{base_url}/images/{raw_rel}",
        annotated_url=(f"{base_url}/images/{ann_rel}" if ann_rel else None),
        ocr_text=img.ocr_text,
        keywords_found=img.keywords_found,
        keyword_score=img.keyword_score,
        flagged=img.keyword_score >= detect_signs.PARKING_FLAG_SCORE,
    )


def _build_response(report: pc.CaptureReport,
                    annotated_paths: Dict[str, str],
                    job_dir: Path,
                    request: ParkingRequest,
                    base_url: str,
                    cleanup_stats: Dict[str, int]) -> ParkingResponse:
    # ---- 1. address_pano_preview: every captured image from the address pano
    address_pano_imgs = [i for i in report.images if i.purpose == "sweep"]
    address_pano_preview: Optional[ParkingLocation] = None
    if address_pano_imgs:
        first = address_pano_imgs[0]
        preview_images = [
            _build_sign_image(i, annotated_paths, base_url)
            for i in sorted(address_pano_imgs, key=lambda x: (x.pitch, x.heading))
        ]
        address_pano_preview = ParkingLocation(
            coordinate={"lat": first.lat, "lng": first.lng},
            pano_id=first.pano_id,
            pano_date=first.pano_date,
            distance_m=round(first.pano_distance_m, 2),
            images=preview_images,
        )

    # ---- 2. parking_locations: panos with at least one flagged image
    by_pano: dict[str, List[pc.CapturedImage]] = {}
    for img in report.images:
        if img.keyword_score < detect_signs.PARKING_FLAG_SCORE:
            continue
        by_pano.setdefault(img.pano_id, []).append(img)

    locations: List[ParkingLocation] = []
    sorted_pids = sorted(by_pano.keys(),
                         key=lambda pid: by_pano[pid][0].pano_distance_m)
    for pid in sorted_pids:
        imgs = sorted(by_pano[pid], key=lambda i: i.heading)
        first = imgs[0]
        sign_images = [_build_sign_image(i, annotated_paths, base_url) for i in imgs]
        locations.append(ParkingLocation(
            coordinate={"lat": first.lat, "lng": first.lng},
            pano_id=pid,
            pano_date=first.pano_date,
            distance_m=round(first.pano_distance_m, 2),
            images=sign_images,
        ))

    return ParkingResponse(
        address_query=request.address,
        resolved_address=report.resolved_address,
        coordinate={"lat": report.lat, "lng": report.lng},
        address_pano_preview=address_pano_preview,
        parking_locations=locations,
        stats={
            "panos_with_signs": len(locations),
            "images_captured": len(report.images),
            "images_kept": cleanup_stats["kept"],
            "images_deleted": cleanup_stats["deleted"],
            "address_preview_images": cleanup_stats["address_preview"],
            "flagged_images": cleanup_stats["flagged"],
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


# ---------------------------------------------------------------------------
# Address autocomplete proxy (Google Places API)
# ---------------------------------------------------------------------------
#
# We proxy Google Places Autocomplete + Place Details so the API key
# never ships in the mobile app. Two endpoints:
#
#   - /places/autocomplete?q=...    -> predictions (place_id + display strings).
#                                       Google does NOT include lat/lng here;
#                                       client follows up with /places/details.
#   - /places/details?place_id=...  -> resolves place_id to lat/lng +
#                                       formatted_address. Called once per
#                                       picked suggestion.
#
# Cost (current pricing, May 2026):
#   - Autocomplete: ~$2.83 / 1000 requests (each debounced keystroke).
#   - Place Details (Basic Data): ~$17 / 1000 requests (once per pick).
# Typical user search: ~5 autocomplete + 1 details = ~3c per search.
# Add session-token plumbing later if call volume grows.

PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


class PlacePrediction(BaseModel):
    """One typeahead suggestion.

    lat/lng are optional because Google's Autocomplete API doesn't
    include coordinates — the client must call /places/details after
    the user picks a suggestion to resolve them. Future provider swaps
    (e.g. Photon, Mapbox) can populate lat/lng inline; the frontend
    treats the field as a hint and falls back to /places/details when
    it's missing.
    """
    place_id: str
    description: str
    main_text: str
    secondary_text: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class PlacesAutocompleteResponse(BaseModel):
    predictions: List[PlacePrediction]


class PlaceDetailsResponse(BaseModel):
    place_id: str
    formatted_address: str
    lat: float
    lng: float


@app.get("/places/autocomplete", response_model=PlacesAutocompleteResponse)
def places_autocomplete(
    q: str = Query(min_length=1, description="Partial address typed by the user"),
    country: str = Query(default="au", description="ISO country bias (default 'au'); empty disables filtering"),
):
    """Proxy Google Places Autocomplete. The mobile app calls this on
    every debounced keystroke and shows the returned predictions inline.
    """
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not google_key:
        raise HTTPException(status_code=500, detail="GOOGLE_MAPS_API_KEY not configured")

    params = {
        "input": q,
        "key": google_key,
    }
    if country:
        params["components"] = f"country:{country}"

    try:
        r = requests.get(PLACES_AUTOCOMPLETE_URL, params=params, timeout=10)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}")

    body = r.json() if r.content else {}
    status = body.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        raise HTTPException(
            status_code=502,
            detail=body.get("error_message") or status or "places autocomplete failed",
        )

    predictions: List[PlacePrediction] = []
    for p in body.get("predictions") or []:
        sf = p.get("structured_formatting") or {}
        predictions.append(PlacePrediction(
            place_id=p.get("place_id") or "",
            description=p.get("description") or "",
            main_text=sf.get("main_text") or "",
            secondary_text=sf.get("secondary_text") or "",
            # lat/lng intentionally None; the frontend resolves via /places/details.
        ))
    return PlacesAutocompleteResponse(predictions=predictions)


@app.get("/places/details", response_model=PlaceDetailsResponse)
def places_details(
    place_id: str = Query(min_length=4, description="place_id from /places/autocomplete"),
):
    """Resolve a Google place_id to lat/lng + formatted address. Called
    once per picked suggestion."""
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not google_key:
        raise HTTPException(status_code=500, detail="GOOGLE_MAPS_API_KEY not configured")

    try:
        r = requests.get(
            PLACES_DETAILS_URL,
            params={
                "place_id": place_id,
                # Restrict to Basic Data fields so we stay in the cheap
                # billing tier. Adding 'address_component' / 'geometry'
                # fields beyond these would tip into Contact / Atmosphere
                # billing. See Google's "Place Data SKUs" doc.
                "fields": "geometry,formatted_address",
                "key": google_key,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}")

    body = r.json() if r.content else {}
    status = body.get("status")
    if status != "OK":
        raise HTTPException(
            status_code=502,
            detail=body.get("error_message") or status or "places details failed",
        )

    result = body.get("result") or {}
    loc = (result.get("geometry") or {}).get("location") or {}
    if "lat" not in loc or "lng" not in loc:
        raise HTTPException(status_code=502, detail="place details missing location")

    return PlaceDetailsResponse(
        place_id=place_id,
        formatted_address=result.get("formatted_address") or "",
        lat=float(loc["lat"]),
        lng=float(loc["lng"]),
    )


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

    # Buffer the log AND echo to stdout so uvicorn shows progress in real
    # time. The buffer is still used for error responses so failed
    # requests can attach a tail of recent log lines.
    log_lines: list[str] = []
    def log(*args):
        line = " ".join(str(a) for a in args)
        log_lines.append(line)
        print(f"[{job_id}] {line}", flush=True)

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
            write_html=False,
            focus=req.focus,
            fetch_workers=req.fetch_workers,
            ocr_workers=req.ocr_workers or None,
            image_quality=req.image_quality,
            max_tile_upgrades=req.max_tile_upgrades,
            log=log,
        )

        cleanup_stats = _cleanup_unflagged_images(report, annotated_paths)
        # Also drop the meta.json from disk - we don't need it after the response.
        meta_file = job_dir / "meta.json"
        if meta_file.exists():
            meta_file.unlink()

        base_url = _resolve_base_url(request)
        response = _build_response(report, annotated_paths, job_dir, req,
                                   base_url, cleanup_stats)

        # If we're not keeping anything (no flagged signs AND no address-pano
        # preview was captured), the job dir is empty - clean it up.
        if cleanup_stats["kept"] == 0:
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
    max_panos: Optional[int] = Query(default=None, ge=1, le=60),
    focus: bool = Query(default=False),
    fetch_workers: int = Query(default=8, ge=1, le=16),
    ocr_workers: int = Query(default=0, ge=0, le=32),
    image_quality: str = Query(default="fast"),
    max_tile_upgrades: int = Query(default=3, ge=1, le=10),
) -> ParkingResponse:
    """Same as POST /parking-signs but as a GET so you can hit it from a
    browser."""
    return find_parking_signs(ParkingRequest(
        address=address, lat=lat, lng=lng,
        radius=radius, headings=headings, pitches=pitches,
        thumbnail_size=thumbnail_size, same_street=same_street,
        max_panos=max_panos,
        focus=focus, fetch_workers=fetch_workers, ocr_workers=ocr_workers,
        image_quality=image_quality, max_tile_upgrades=max_tile_upgrades,
    ), request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
