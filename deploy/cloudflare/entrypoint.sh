#!/bin/bash
set -euo pipefail
mkdir -p /data/uploads
cd /app/backend
python -c "from cncflow_core.common.persist import restore_db; restore_db()"
python -c "from cncflow_core.common.db import get_conn, init_schema; conn=get_conn(); init_schema(conn); conn.close()"
python -m cncflow_core.common.persist &
python -m cncflow_core.ingestion.worker &
exec gunicorn --bind 0.0.0.0:5001 --workers 1 --threads 4 --timeout 300 "app:create_app()"
