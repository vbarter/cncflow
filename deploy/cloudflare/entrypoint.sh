#!/bin/bash
set -euo pipefail
mkdir -p /data/uploads /app/chat-jail/docs /app/chat-jail/backend /app/chat-jail/frontend
if [ -d /app/docs/knowledge-base ]; then
  rm -rf /app/chat-jail/docs/knowledge-base
  cp -a /app/docs/knowledge-base /app/chat-jail/docs/knowledge-base
fi
if [ -d /app/backend/cncflow_core ]; then
  rm -rf /app/chat-jail/backend/cncflow_core
  cp -a /app/backend/cncflow_core /app/chat-jail/backend/cncflow_core
fi
if [ -d /app/frontend/src ]; then
  rm -rf /app/chat-jail/frontend/src
  cp -a /app/frontend/src /app/chat-jail/frontend/src
fi

export CHAT_JAIL="${CHAT_JAIL:-/app/chat-jail}"
export CHAT_PORT="${CHAT_PORT:-3002}"
export CHAT_HOST="${CHAT_HOST:-0.0.0.0}"
export TUZI_MODEL="${TUZI_MODEL:-gpt-4.1-mini}"
export TUZI_BASE_URL="${TUZI_BASE_URL:-https://api.tu-zi.com/v1}"

if [ -f /app/chat/dist/server.js ]; then
  node /app/chat/dist/server.js &
fi

cd /app/backend
python -c "from cncflow_core.common.persist import restore_db; restore_db()"
python -c "from cncflow_core.common.db import get_conn, init_schema; conn=get_conn(); init_schema(conn); conn.close()"
python -m cncflow_core.common.persist &
python -m cncflow_core.ingestion.worker &
exec gunicorn --bind 0.0.0.0:5001 --workers 1 --threads 4 --timeout 300 "app:create_app()"
