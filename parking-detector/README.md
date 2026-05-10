# Parking Sign Capture — Street View + Tesseract (free, simple)

Give it an Australian street address. The script:

1. Geocodes the address.
2. Discovers every distinct Google Street View panorama within `--radius`
   metres of the address (free metadata calls — no quota cost).
3. Sweeps every pano with `--headings` evenly-spaced compass headings
   (default 8). At every radius pano the sweep starts pointing at the
   address, so the first frame is always aimed inwards.
4. Runs **Tesseract OCR locally** on every captured image and scores
   the recognised text against parking keywords (1P/2P/4P, MON-FRI,
   AM/PM, time ranges, ZONE, STOPPING, …).
5. Builds a self-contained HTML page where every image is grouped by
   its source pano, sorted by distance from the address, with the OCR
   text underneath. Images whose OCR text scored above the parking
   keyword threshold get a green border.

Free except for Google Maps captures (covered by the free $200/month
Maps credit for ~500 lookups at default settings).

> **Honest expectations.** Tesseract is generic. It struggles with
> Australian sign fonts, especially at distance and in the 640×640
> images Google's free tier returns. Treat green-border highlights as
> "look here first", not "this is definitive". The contact sheet exists
> precisely so you can scroll through and read the signs by eye too.

---

## Algorithm flowchart

```
┌────────────────────────────────────────┐
│ Address (text input)                   │
└──────────────────┬─────────────────────┘
                   │  Google Geocoding API   ($0.005)
                   ▼
┌────────────────────────────────────────┐
│ Lat / lng                              │
└──────────────────┬─────────────────────┘
                   │  Google Street View Metadata API   (free)
                   │  - probe centre + concentric rings
                   │    (15 m, 30 m, 45 m, …) up to --radius
                   │  - dedupe by pano_id
                   ▼
┌────────────────────────────────────────┐
│ List of N distinct panos within radius │
└──────────────────┬─────────────────────┘
                   │  (default ON when --radius > 0)
                   │  Reverse-geocode every candidate pano
                   │  ($0.005/pano) → keep only those whose
                   │  street name matches the address.
                   │  Address pano always kept regardless.
                   │  Disable with --no-same-street.
                   ▼
┌────────────────────────────────────────┐
│ Panos on the SAME STREET as address    │
│ (sorted by distance, capped at         │
│  --max-panos beyond the address pano)  │
└──────────────────┬─────────────────────┘
                   │  Google Street View Static API   ($0.007/img)
                   │  for each pano:
                   │    for each heading in --headings (default 8):
                   │      for each pitch in --pitches (default 1):
                   │        for each fov in --fovs (default 1):
                   │          fetch image
                   │  (radius panos start their sweep aimed at address)
                   ▼
┌────────────────────────────────────────┐
│ Captured images on disk                │
└──────────────────┬─────────────────────┘
                   │  Tesseract OCR   (local, free)
                   │  - preprocess (grayscale + CLAHE + threshold)
                   │  - per-word confidence filter (≥ 40)
                   │  - word-boundary keyword match:
                   │    STRONG (NO STOPPING, P-codes, time
                   │    ranges) → 3 pts each
                   │    WEAK (MON, FRI, AM, PM, ...) → 0.5 pts
                   ▼
┌────────────────────────────────────────┐
│ Per-image OCR text + keyword score     │
│ Flag any image with score ≥ 3.0        │
└──────────────────┬─────────────────────┘
                   │  (optional) draw bounding boxes around
                   │  every word Tesseract recognised
                   │  (green = parking keyword, grey = other)
                   ▼
┌────────────────────────────────────────┐
│ index.html (contact sheet, grouped     │
│  by pano, flagged images highlighted)  │
└────────────────────────────────────────┘
```

The whole thing is just **capture wide → OCR everything → highlight
matches**. There's no "clever" auto-zoom or score-based capture-
triggering anymore — those were silently failing when one piece
misjudged. Now every image is treated equally, and you decide what's
real.

---

## What you need

1. **Python 3.9+**.
2. **A Google Cloud API key** with Geocoding API + Street View Static API enabled.
3. **Tesseract OCR installed on your system** (binary, not just the Python wrapper).
4. **OpenCV** (Python wheel — installed automatically by `pip`).

### Install Tesseract

**macOS** (Homebrew):
```bash
brew install tesseract
```

**Ubuntu / Debian / WSL**:
```bash
sudo apt update && sudo apt install -y tesseract-ocr
```

**Windows**: installer at <https://github.com/UB-Mannheim/tesseract/wiki>,
then add `C:\Program Files\Tesseract-OCR` to your PATH.

Verify: `tesseract --version` should print `tesseract 4.x` or later.

### Get the Google Maps API key

1. <https://console.cloud.google.com/> → sign in → New Project.
2. Search & **enable** these two APIs:
   - **Geocoding API**
   - **Street View Static API**
3. APIs & Services → Credentials → **+ Create Credentials → API key**. Copy.
4. (Recommended) **Restrict key** → API restrictions → limit to those two APIs.

---

## Install

```bash
cd parking-detector/
python3 -m venv .venv
source .venv/bin/activate         # macOS / Linux
# .venv\Scripts\activate          # Windows PowerShell

pip install -r requirements.txt

cp .env.example .env
# open .env, paste your Google Maps key
```

---

## Run it

Basic — just the address pano (8 captures, ~6 c):

```bash
python parking_check.py "12 Smith Street, Fitzroy VIC 3065"
```

Recommended — sweep nearby panos AND capture each heading at two FOVs
(wide overview + sharp narrow zoom). Reads distant signs much better:

```bash
python parking_check.py "12 Smith St, Fitzroy" --radius 50 --fovs "80,30"
```

Output:

```
[1/4] Geocoding: '12 Smith Street, Fitzroy VIC 3065'
      -> 12 Smith St, Fitzroy VIC 3065, Australia  (-37.798321, 144.978654)
[2/4] Discovering Street View panos within 50m...
      found 7 pano(s); using 7 (address pano + 6 others)
        ABCxyz123456.. at 0.0m, date 2024-03
        DEFghi789012.. at 14.2m, date 2024-03
        ...
[3/4] Capturing 8 headings x 1 pitch(es) from 7 pano(s) = 56 images...
      saved addr_pano_h000_p+10.jpg
      ...
[4/4] OCR + annotate every image (56 total)...
      (  1/ 56) addr_pano_h000_p+10.jpg  score=0.0
      (  2/ 56) addr_pano_h045_p+10.jpg  score=3.5 [PARKING]
      ...

Done. 56 image(s) captured.
  Flagged as parking-like: 4 (keyword score >= 3.0)
```

Open `report/index.html` in a browser. Every image is grouped by the
pano it came from, sorted by distance from the address. Anything that
OCR'd as parking-like has a green border, and every recognised word
gets a small bounding box drawn over the image so you can see exactly
what Tesseract picked up.

### Useful flags

| Flag                  | What it does                                                  |
| --------------------- | ------------------------------------------------------------- |
| `--radius 50`         | Scan all panos within 50 m. **0 = address pano only.**         |
| `--max-panos 10`      | Cap on extra panos beyond the address pano (default 10).     |
| `--same-street`       | **Default ON** — only keep panos on the same street as the address. Disable with `--no-same-street` for a full radius circle (which will include cross-streets and back lanes). |
| `--headings 8`        | Number of headings per pano (default 8).                     |
| `--pitches "0"`       | Comma-separated pitches per heading. Try `"0,10,-5"` for varying sign heights. |
| `--fovs "80"`         | Comma-separated FOVs. **Try `"80,30"` for sharp distant signs.** |
| `--use-thumbnail`     | Fetch via the unofficial `streetviewpixels-pa.googleapis.com/v1/thumbnail` endpoint. Higher resolution, no per-image cost, but ToS gray area and `--fovs` is ignored. See "Thumbnail mode" below. |
| `--thumbnail-size 1280x720` | Output WxH for thumbnail captures. Try `1600x900` or `2048x1152` for sharper. |
| `--no-ocr`            | Skip OCR. Just capture images.                               |
| `--no-annotate`       | Skip drawing per-word boxes on the contact sheet.            |
| `--zoom 252:25:-5`    | Manual close-up: heading=252°, fov=25°, pitch=-5°. Repeatable. From the address pano. |
| `--out ./somewhere`   | Output directory (default `./report`).                       |

### Recommended `--radius` settings

With `--same-street` on (the default), `--radius` is roughly "how far
up and down this street do you want to look":

- **0** (default) — address pano only, ~6 c per address.
- **30** — typical inner-city, finds 2–4 same-street panos (~20 c).
- **50** — finds 4–7 same-street panos (~30 c).
- **100** — whole block frontage, both sides if same street (~50 c).

With `--no-same-street`, all the above counts roughly double because
you'll also pick up cross-streets and back lanes. Use that only when
you actually want to scan an area, not a street.

Metadata probes are free regardless of `--radius`. Reverse-geocoding
each candidate pano for the same-street check costs ~$0.005 per pano,
which is usually paid back by skipping the captures from rejected
panos.

### Thumbnail mode (`--use-thumbnail`) — higher resolution, free captures, ToS gray area

Google Maps' web client renders Street View thumbnails through an internal
endpoint:

```
https://streetviewpixels-pa.googleapis.com/v1/thumbnail
  ?output=thumbnail
  &cb_client=maps_sv.tactile.gps
  &panoid=PANOID
  &w=1280&h=720
  &thumb=3
  &yaw=HEADING
  &pitch=PITCH
```

`yaw` and `pitch` rotate the view exactly the same way `--headings` and
`--pitches` do for the Static API. The big difference is **resolution**:
the Static API caps at 640 × 640 on the free tier, while the thumbnail
endpoint will serve up to ~2048 × 1152. That's ~5× the pixels, which
makes Tesseract dramatically more reliable at reading distant signs.

**Pros:**
- Higher resolution (set with `--thumbnail-size 1600x900` or larger).
- No per-image cost.
- No API key needed for the captures themselves (you still need the key
  for geocoding + metadata pano discovery, but those are dirt cheap).

**Cons:**
- **Undocumented.** Google can change or disable this endpoint without
  notice. The script will surface failures as `(no imagery ...)` lines
  in the log if that happens.
- **No FOV control.** The thumbnail endpoint doesn't accept a `fov`
  parameter. The angular field of view is fixed by the requested
  aspect ratio + the `thumb=3` variant. So `--fovs` is silently
  ignored when `--use-thumbnail` is on.
- **Maps Platform ToS gray area.** Google's terms prohibit "scraping"
  and "use of services other than as documented". Low-volume personal
  use is unlikely to attract attention; bulk or commercial use isn't
  safe here.
- **Rate limits by IP.** High-volume use will get your IP throttled or
  blocked. The script doesn't add explicit delays — be mindful.

**Recommended use:**

```bash
# Same-street radius scan, higher resolution, no per-image cost
python parking_check.py "Unit 1/4-8 Osborne St, South Yarra VIC 3141" \
  --radius 50 --use-thumbnail --thumbnail-size 1600x900
```

Cost reduces to just the geocode + reverse-geocodes for `--same-street`
(~$0.05 per address total). The captures themselves are free.

### Why are the captured images blurrier than what I see in Google Maps?

Google's interactive Street View streams full-resolution panorama
tiles, but the **Static API caps free-tier images at 640 × 640**.
With the default FOV=80°, that means each pixel covers ~0.125° of
view — a 30 cm parking sign 30 m away ends up around **4 pixels
wide**, well below what Tesseract can read.

The fix is to capture at a narrower FOV. Same image budget, smaller
angular slice = each pixel covers less, distant objects appear larger
and sharper. At FOV=30°, that 30 cm sign at 30 m is about 12 pixels —
borderline-readable.

Use **`--fovs "80,30"`** to capture every heading at *both* FOVs. The
wide one gives you situational awareness; the narrow one gives
Tesseract enough resolution to actually read distant signs. Doubles
the capture count (cost too) but is the single most effective change
for OCR accuracy on signs more than ~15 m from the camera.

### Why do I sometimes see green borders on images that DON'T have parking signs?

Tesseract hallucinates text in noise. If you see a flagged image
that obviously has no sign, the algorithm has been deliberately
tightened to make this rare:

- Keywords are matched with **word boundaries**, so "MON" inside
  "MONITORING" won't trigger.
- Words with Tesseract per-word confidence below 40 are dropped
  (the raw text is still preserved in `meta.json` if you want it).
- Weak keywords (MON, FRI, AM, PM) are worth only 0.5 points each;
  flagging requires score ≥ 3.0. So even four random weak hits
  don't flag.
- Strong indicators that DO flag alone: any P-code (1P/2P/4P), any
  multi-word keyword like NO STOPPING / LOADING ZONE / PERMIT ZONE,
  or a real time range with a colon ("8:30-18:30").

If you still see false positives on noisy images, look at the
annotated copy in `report/annotated/`: green boxes show every word
Tesseract claimed to read above the confidence threshold. Compare
with the source image — if the boxes are over noise rather than
text, that's a Tesseract failure mode you can't fix without a
better OCR.

### What if a sign you can see by eye isn't flagged?

Three usual causes:

1. **The image is too low-res to read.** This is the FOV=80 problem.
   Re-run with `--fovs "80,30"` so every heading is captured at a
   tighter zoom too. Or use `--zoom HEADING:25:PITCH` to grab a
   surgical close-up at the specific heading you spotted the sign at
   (find the heading by clicking on the pano in the Google Maps URL —
   the `yaw` parameter is the heading, the `pitch` parameter is the
   pitch).

2. **The sweep didn't include the right pitch.** Default is `--pitches "0"`
   (eye level). Signs on hilly streets, or far down a long street, can
   sit slightly above or below. Try `--pitches "0,10,-5"` (triples
   capture count but covers all reasonable sign heights).

3. **The pano sweep didn't include the right heading.** With
   `--headings 8` the sampled headings are 45° apart. A sign on a thin
   pole might fall between two of those captures. Try `--headings 12`
   (every 30°) or `--headings 16` (every 22.5°).

The escape hatch is always **manual `--zoom`** for surgical follow-up
on a specific direction.

---

## HTTP API (FastAPI)

The same pipeline is exposed as a small HTTP service in `api.py`. Use
this if you want to call it from another app, a frontend, or a batch
job rather than from the CLI.

### Run the server

```bash
# In the same venv, with .env populated:
uvicorn api:app --host 0.0.0.0 --port 8000

# OR (auto-reload while developing)
python api.py
```

Interactive docs: <http://localhost:8000/docs>.

### Endpoints

#### `POST /parking-signs`

Body (JSON):

```json
{
  "address": "Unit 1/4-8 Osborne St, South Yarra VIC 3141",
  "radius": 50,
  "headings": 8,
  "pitches": "0",
  "thumbnail_size": "1600x900",
  "same_street": true,
  "max_panos": 10
}
```

Either `address` OR (`lat` and `lng`) is required. Everything else is
optional with the defaults above.

Response (200):

```json
{
  "address_query": "Unit 1/4-8 Osborne St, South Yarra VIC 3141",
  "resolved_address": "1 Osborne St, South Yarra VIC 3141, Australia",
  "coordinate": {"lat": -37.8459485, "lng": 144.9901652},
  "parking_locations": [
    {
      "coordinate": {"lat": -37.8459485, "lng": 144.9901652},
      "pano_id": "vWPh3K8INDWjauVgAC71Cw",
      "pano_date": "2024-03",
      "distance_m": 16.0,
      "images": [
        {
          "heading": 254,
          "pitch": 0,
          "url": "http://localhost:8000/images/abc123def456/images/radius_016m_..._h254_p+00_thumb.jpg",
          "annotated_url": "http://localhost:8000/images/abc123def456/annotated/radius_016m_..._h254_p+00_thumb.jpg",
          "ocr_text": "2P. MON-FRI 8:30AM 6:30PM",
          "keywords_found": ["2P", "MON", "FRI"],
          "keyword_score": 4.0
        }
      ]
    }
  ],
  "stats": {
    "panos_with_signs": 1,
    "images_captured": 56,
    "images_kept": 4,
    "images_deleted": 52
  }
}
```

The `url` and `annotated_url` fields are **absolute URLs** including
host and port (e.g. `http://localhost:8000/images/...`), so a frontend
or downstream service can fetch them directly without joining a base
path. By default the URL is derived from the request's `Host` header.
For deployments behind nginx / a load balancer, see "Behind a reverse
proxy" below.

They serve the surviving JPEGs straight from disk — every captured
image that didn't reach the parking-keyword threshold
(`PARKING_FLAG_SCORE = 3.0`) is **deleted from disk** before the
response is returned. So a `200` response is the only reference to
those images that exists on the server.

Errors:

- `400` — Bad input (missing address and lat/lng, malformed thumbnail_size).
- `404` — No Street View imagery near the address.
- `422` — Pydantic validation error on the body.
- `500` — `GOOGLE_MAPS_API_KEY` is not set, or an unexpected error.
- `502` — Capture failed even though imagery exists.

#### `GET /parking-signs?address=...`

Same as POST but with query string parameters, so you can hit it from a
browser. Note that `lat`, `lng` are split into separate query params.

#### `GET /health`

Quick readiness check:

```json
{
  "status": "ok",
  "google_key_present": true,
  "tesseract_available": true,
  "results_dir": "/abs/path/to/api_results"
}
```

### Image cleanup

The API always uses the **thumbnail backend** (`--use-thumbnail`
equivalent), so captures are free. After every request:

1. Tesseract runs on every captured image.
2. Any image whose keyword score is below the parking threshold (3.0)
   is **deleted from disk** along with its annotated copy.
3. The response references only the surviving flagged images.
4. If nothing flagged, the entire job directory is wiped.

So at any given time, the only images on disk are those that scored as
parking-relevant in some prior request.

### Where images live

Each request gets its own job directory under `api_results/<job_id>/`.
You can change the root with the `PARKING_RESULTS_DIR` environment
variable. There's no automatic expiry — set up a cron job if you need
one (e.g. `find api_results/ -mtime +7 -delete`).

### Quick curl example

```bash
# POST
curl -X POST http://localhost:8000/parking-signs \
  -H 'Content-Type: application/json' \
  -d '{
    "address": "Unit 1/4-8 Osborne St, South Yarra VIC 3141",
    "radius": 50,
    "thumbnail_size": "1600x900"
  }'

# GET (browser-friendly)
curl 'http://localhost:8000/parking-signs?address=Unit%201%2F4-8%20Osborne%20St%2C%20South%20Yarra&radius=50'

# Then fetch one of the returned image URLs
curl http://localhost:8000/images/abc123def456/images/radius_016m_..._h254_p+00_thumb.jpg \
  -o sign.jpg
```

### Behind a reverse proxy

If you put the API behind nginx / Cloudflare / a load balancer, the
auto-detected base URL might be the *internal* host (`http://localhost:8000`)
rather than the public one. Two ways to fix:

**Option A — uvicorn proxy headers.** Start uvicorn with
`--proxy-headers --forwarded-allow-ips="*"` so it respects
`X-Forwarded-Proto` and `X-Forwarded-Host` set by your proxy:

```bash
uvicorn api:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips="*"
```

Then configure nginx to pass the headers:

```nginx
location / {
  proxy_set_header Host              $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-Host  $host;
  proxy_pass http://127.0.0.1:8000;
}
```

**Option B — environment variable override.** If you want absolute
control, set `PUBLIC_BASE_URL` to the user-facing URL:

```bash
PUBLIC_BASE_URL="https://parking.example.com" \
  uvicorn api:app --host 127.0.0.1 --port 8000
```

Every response will use that base regardless of what headers come in.

### Security notes

This API runs paid Google Geocoding calls per request. **Do not expose
it to the public internet without auth + rate limits.** A reasonable
deployment is behind nginx with HTTP basic auth or a token, on a
private network, or behind a `tailscale serve` tunnel. The script
itself adds none of that.

---

## What you get back (CLI mode)

```
report/
├── index.html        open this in a browser
├── meta.json         everything machine-readable, including OCR text
├── images/           every captured JPG
│   ├── addr_pano_h000_p+00_f080.jpg     (heading 0, pitch 0, FOV 80)
│   ├── addr_pano_h000_p+00_f030.jpg     (same view at narrow FOV, sharp)
│   ├── addr_pano_h045_p+00_f080.jpg
│   ├── ...
│   ├── radius_014m_DEFghi78_h252_p+00_f080.jpg
│   ├── ...
│   └── manual_01_h252_p-05.jpg          (if --zoom used)
└── annotated/        copies with green/grey boxes around every word
                      Tesseract recognised (green = parking keyword)
```

---

## Cost

Google Maps Platform free tier is **$200 of credit per month**. Image
captures are $0.007 each. Geocoding is $0.005.

| Setup                                              | Captures  | Cost      | Lookups / month |
| -------------------------------------------------- | --------: | --------: | --------------: |
| `--radius 0` (address only, default)               |         8 |  ~6 c     | ~3,300          |
| `--radius 30`                                      |    ~30-50 | ~25 c     |   ~800          |
| `--radius 50`                                      |    ~50-80 | ~40 c     |   ~500          |
| `--radius 50 --fovs "80,30"`                       |   ~100-160| ~75 c     |   ~265          |
| `--radius 50 --use-thumbnail`                      |    ~50-80 | **~5 c**  | ~4,000          |
| `--radius 50 --use-thumbnail --thumbnail-size 1600x900` | ~50-80 | **~5 c**  | ~4,000          |

If you stay under $200, you pay nothing. Tesseract + OpenCV run
locally — no extra cost. Metadata probes for pano discovery are also
free regardless of `--radius`.

---

## Limitations & honest caveats

- **Stale imagery.** Pano dates can be years old. They're shown in the
  HTML so you know.
- **Tesseract is generic.** It misses 30-50 % of Australian parking
  signs in our testing, especially at distance. A green-border
  highlight is a strong hint, but the absence of one is not proof
  there's no sign — that's why every captured image is shown, not just
  the flagged ones.
- **Sign-zone-to-property mapping is not done.** The script tells you
  what signs sit near the kerb. Working out which metres of kerb each
  sign actually governs (arrows, overlapping zones) is left to you.
- **Coverage gaps.** Quiet residential, laneways, rural — no Street
  View. Script exits 3.
- **Free-tier resolution.** Captures are capped at 640 × 640. A sign
  far down the street may be too small to OCR even with `--zoom`.

---

## Files in this folder

```
parking-detector/
├── README.md            this file
├── parking_check.py     CLI + run_parking_check() function
├── detect_signs.py      Tesseract OCR + scoring helpers
├── api.py               FastAPI server (POST /parking-signs)
├── requirements.txt     Python dependencies
├── .env.example         template for your Google key
├── .gitignore
├── report/              created by CLI runs
└── api_results/         created by API runs (auto-cleaned to keep
                         only flagged images per request)
```

---

## Troubleshooting

**`tesseract binary not installed`** in the OCR text field
You skipped the OS-level Tesseract install — re-read the install section.

**`OCR module not available: No module named 'cv2'`**
Run `pip install -r requirements.txt` again, ideally inside a venv.

**`Geocode failed: status=REQUEST_DENIED`**
Geocoding API isn't enabled on your Google project, or your key is
restricted in a way that excludes it.

**Images come back tiny / `http 403`**
Street View Static API not enabled, or billing not configured (free
tier still requires billing to be set up — you just won't be charged
unless you exceed the credit).

**`No Street View imagery near this address`**
No pano nearby. Try a different address or a coordinate slightly
along the road.

**Captured but nothing flagged, even though I can see a sign**
See "What if a sign you can see by eye isn't flagged?" above.
