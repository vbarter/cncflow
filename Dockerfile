FROM node:22-bookworm-slim AS node

FROM python:3.11-slim-bookworm

COPY --from=node /usr/local /usr/local

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libglu1-mesa libxrender1 libsm6 libxext6 \
        tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements-parser.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements-parser.txt

COPY backend /app/backend
COPY docs /app/docs
COPY frontend/src /app/frontend/src
COPY chat /app/chat
COPY deploy/cloudflare/entrypoint.sh /entrypoint.sh

WORKDIR /app/chat
RUN npm ci && npm run build && npm prune --omit=dev

RUN chmod +x /entrypoint.sh \
    && mkdir -p /data/uploads /app/chat-jail \
    && mkdir -p /app/chat-jail/docs /app/chat-jail/backend /app/chat-jail/frontend \
    && cp -a /app/docs/knowledge-base /app/chat-jail/docs/knowledge-base \
    && cp -a /app/backend/cncflow_core /app/chat-jail/backend/cncflow_core \
    && cp -a /app/frontend/src /app/chat-jail/frontend/src

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    CNCFLOW_DB_PATH=/data/cncflow.db \
    CNCFLOW_REQUIRE_PERSISTENT_DB=1 \
    CNCFLOW_FILE_STORAGE=/data/uploads \
    CHAT_JAIL=/app/chat-jail \
    CHAT_PORT=3002 \
    CHAT_HOST=0.0.0.0 \
    TUZI_MODEL=gpt-4.1-mini \
    TUZI_BASE_URL=https://api.tu-zi.com/v1

WORKDIR /app/backend
EXPOSE 5001 3002
ENTRYPOINT ["/entrypoint.sh"]
