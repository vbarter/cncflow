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

# CadQuery/OCP 在无桌面 Linux 上仍会动态加载 libGL.so.1；缺失时 Python
# 包虽然安装成功，但直到真正解析 STP 才会报 ImportError。
if ! ldconfig -p 2>/dev/null | grep -q 'libGL\.so\.1' \
   || ! command -v tesseract >/dev/null 2>&1 \
   || ! tesseract --list-langs 2>/dev/null | grep -q '^chi_sim$'; then
  apt-get update -qq
  apt-get install -y -qq libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
fi
if [ ! -d backend/.venv-parser ]; then
  "${PARSER_PYTHON:-python3}" -m venv backend/.venv-parser
fi
backend/.venv-parser/bin/pip install -q -r backend/requirements-parser.txt
# 部署阶段就验证原生依赖，避免 Worker 看似在线、收到任务后才失败。
backend/.venv-parser/bin/python -c "import cadquery; from OCP.gp import gp_Pnt"

install -m 0644 deploy/cncflow.service /etc/systemd/system/cncflow.service
install -m 0644 deploy/cncflow-parser.service /etc/systemd/system/cncflow-parser.service
install -m 0644 deploy/nginx-cncflow.conf /etc/nginx/conf.d/cncflow.conf
systemctl daemon-reload
systemctl enable cncflow-parser >/dev/null

systemctl restart cncflow-parser
systemctl restart cncflow
systemctl is-active --quiet cncflow-parser
nginx -t
systemctl reload nginx

sleep 2
curl -sf http://127.0.0.1:5001/api/v1/health
echo
echo "deploy ok: $(git rev-parse --short HEAD)"
