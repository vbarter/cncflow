FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libglu1-mesa libxrender1 libsm6 libxext6 \
        tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements-parser.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements-parser.txt

COPY backend /app/backend
COPY deploy/cloudflare/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /data/uploads

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    CNCFLOW_DB_PATH=/data/cncflow.db \
    CNCFLOW_REQUIRE_PERSISTENT_DB=1 \
    CNCFLOW_FILE_STORAGE=/data/uploads

WORKDIR /app/backend
EXPOSE 5001
ENTRYPOINT ["/entrypoint.sh"]
