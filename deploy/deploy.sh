#!/usr/bin/env bash
# cncflow 服务器端部署脚本：由 GitHub Actions SSH 触发（也可手动执行）
set -euo pipefail

cd /root/dev/cncflow
git pull --ff-only origin main

mkdir -p /var/lib/cncflow/files
chmod 750 /var/lib/cncflow/files

if [ ! -x backend/.venv/bin/python ]; then
  python3 -m venv backend/.venv
fi

backend/.venv/bin/pip install -q -r backend/requirements.txt
backend/.venv/bin/python deploy/seed_if_empty.py

if ! command -v tesseract >/dev/null 2>&1 || ! tesseract --list-langs 2>/dev/null | grep -q '^chi_sim$'; then
  apt-get update -qq
  apt-get install -y -qq tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
fi
if [ ! -d backend/.venv-parser ]; then
  "${PARSER_PYTHON:-python3}" -m venv backend/.venv-parser
fi
backend/.venv-parser/bin/pip install -q -r backend/requirements-parser.txt

install -m 0644 deploy/cncflow.service /etc/systemd/system/cncflow.service
install -m 0644 deploy/cncflow-parser.service /etc/systemd/system/cncflow-parser.service
install -m 0644 deploy/nginx-cncflow.conf /etc/nginx/conf.d/cncflow.conf
systemctl daemon-reload
systemctl enable cncflow-parser >/dev/null

systemctl restart cncflow-parser
systemctl restart cncflow
nginx -t
systemctl reload nginx

sleep 2
curl -sf http://127.0.0.1:5001/api/v1/health
echo
echo "deploy ok: $(git rev-parse --short HEAD)"
