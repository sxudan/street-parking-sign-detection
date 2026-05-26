# Parking Sign Detector API — Google Cloud Run
#
# Build (from this directory):
#   docker build -t parking-detector .
#
# Run locally:
#   docker run --rm -p 8080:8080 \
#     -e GOOGLE_MAPS_API_KEY=your-key \
#     parking-detector
#
# Deploy to Cloud Run (example):
#   gcloud run deploy parking-detector \
#     --source . \
#     --region australia-southeast1 \
#     --set-env-vars GOOGLE_MAPS_API_KEY=your-key \
#     --memory 2Gi --cpu 2 --timeout 900 \
#     --allow-unauthenticated

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OCR_BACKEND=rapid \
    PARKING_RESULTS_DIR=/tmp/api_results \
    PORT=8080

WORKDIR /app

# OpenCV + onnxruntime runtime deps on slim Debian.
# rapidocr-onnxruntime installs opencv-python, which needs libxcb on headless images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        libgl1 \
        libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py parking_check.py detect_signs.py tile_fetcher.py ./

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /tmp/api_results \
    && chown -R appuser:appuser /app /tmp/api_results

USER appuser

EXPOSE 8080

# Cloud Run sets PORT. --proxy-headers so image URLs use the public HTTPS host.
CMD ["sh", "-c", "exec uvicorn api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
