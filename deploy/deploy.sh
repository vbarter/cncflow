#!/usr/bin/env bash
# cncflow 服务器端部署脚本：由 GitHub Actions SSH 触发（也可手动执行）
set -euo pipefail

cd /root/dev/cncflow
git pull --ff-only origin main

backend/.venv/bin/pip install -q -r backend/requirements.txt
backend/.venv/bin/python deploy/seed_if_empty.py

systemctl restart cncflow

sleep 2
curl -sf http://127.0.0.1:5001/api/v1/health
echo
echo "deploy ok: $(git rev-parse --short HEAD)"
