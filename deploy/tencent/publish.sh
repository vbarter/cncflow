#!/usr/bin/env bash
# Publish Vite dist to Tencent VPS as static nginx (port 8081).
# API stays on the Cloudflare Worker — nginx reverse-proxies /api.
#
# Local (HostAlias already set):
#   ./deploy/tencent/publish.sh
#
# CI / box without HostAlias:
#   TENCENT_SSH_HOST=root@43.129.175.172 TENCENT_SSH_PRIVATE_KEY=... ./deploy/tencent/publish.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF="$(cd "$(dirname "$0")" && pwd)/nginx-cncflow-static.conf"

TENCENT_SSH_HOST="${TENCENT_SSH_HOST:-tencent}"
TENCENT_HOST_IP="${TENCENT_HOST_IP:-43.129.175.172}"
TENCENT_WEB_ROOT="${TENCENT_WEB_ROOT:-/var/www/cncflow}"
TENCENT_NGINX_CONF="${TENCENT_NGINX_CONF:-/etc/nginx/conf.d/cncflow-static.conf}"
PUBLIC_URL="${TENCENT_PUBLIC_URL:-http://43.129.175.172:8081/}"
SKIP_BUILD=0
SKIP_NGINX=0
DIST=""

usage() {
  sed -n '2,12p' "$0"
  echo
  echo "Flags:"
  echo "  --skip-build    use existing frontend/dist (must be VITE_BASE=/ and no VITE_API_URL)"
  echo "  --skip-nginx    rsync dist only; do not install/reload nginx conf"
  echo "  --dist DIR      rsync this directory instead of frontend/dist"
  echo "  --check         local sanity checks only (no SSH)"
  echo "  -h, --help"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-build) SKIP_BUILD=1 ;;
    --skip-nginx) SKIP_NGINX=1 ;;
    --dist)
      DIST="${2:?--dist requires a directory}"
      shift
      ;;
    --check)
      exec "$(cd "$(dirname "$0")" && pwd)/check.sh"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

DIST="${DIST:-$ROOT/frontend/dist}"

if [ "$SKIP_BUILD" -eq 0 ]; then
  # Same-origin /api via nginx. Do not bake VITE_API_URL (that is the Pages build).
  (
    cd "$ROOT/frontend"
    npm ci
    VITE_BASE=/ env -u VITE_API_URL npm run build
  )
fi

if [ ! -f "$DIST/index.html" ]; then
  echo "missing $DIST/index.html — build first or pass --dist" >&2
  exit 1
fi

if grep -q 'cncflow-api\.yzcaijunjie6095\.workers\.dev' "$DIST"/assets/*.js 2>/dev/null; then
  echo "warning: dist still contains VITE_API_URL (Pages build)." >&2
  echo "  Browser will call the Worker cross-origin; nginx /api proxy unused." >&2
  echo "  CORS fallback: allow http://43.129.175.172:8081 on CNCFLOW_CORS_ORIGINS." >&2
  echo "  Rebuild without VITE_API_URL for same-origin /api." >&2
fi

SSH_OPTS=()
KEY=""
cleanup() {
  if [ -n "$KEY" ]; then
    rm -f "$KEY"
  fi
}
trap cleanup EXIT

if [ -n "${TENCENT_SSH_PRIVATE_KEY:-}" ]; then
  KEY="$(mktemp)"
  printf '%s\n' "$TENCENT_SSH_PRIVATE_KEY" > "$KEY"
  chmod 600 "$KEY"
  SSH_OPTS+=(-i "$KEY")
fi
SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
ssh-keyscan -H "$TENCENT_HOST_IP" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true

ssh_cmd() {
  ssh "${SSH_OPTS[@]}" "$TENCENT_SSH_HOST" "$@"
}

echo "rsync $DIST/ -> ${TENCENT_SSH_HOST}:${TENCENT_WEB_ROOT}/"
ssh_cmd "mkdir -p '$TENCENT_WEB_ROOT'"
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "$DIST/" "${TENCENT_SSH_HOST}:${TENCENT_WEB_ROOT}/"

if [ "$SKIP_NGINX" -eq 0 ]; then
  echo "install nginx site $TENCENT_NGINX_CONF (listen 8081 only)"
  scp "${SSH_OPTS[@]}" "$CONF" "${TENCENT_SSH_HOST}:${TENCENT_NGINX_CONF}.new"
  ssh_cmd "bash -s" <<REMOTE
set -euo pipefail
if ! command -v nginx >/dev/null; then
  echo "nginx not found on remote; install it without changing magicart vhosts" >&2
  exit 1
fi
# Refuse to steal 8081 from a foreign process (magicart is 80/443; 8080 is occupied).
if command -v ss >/dev/null && ss -lntp 2>/dev/null | grep -q ':8081 ' && [ ! -f '$TENCENT_NGINX_CONF' ]; then
  echo "port 8081 already bound and $TENCENT_NGINX_CONF is absent; abort" >&2
  ss -lntp | grep 8081 || true
  exit 1
fi
install -m 0644 '${TENCENT_NGINX_CONF}.new' '$TENCENT_NGINX_CONF'
rm -f '${TENCENT_NGINX_CONF}.new'
nginx -t
systemctl reload nginx
REMOTE
fi

echo "smoke ${PUBLIC_URL}"
ssh_cmd "curl -sfS --max-time 15 http://127.0.0.1:8081/ | grep -q 'id=\"root\"'"
ssh_cmd "curl -sfS --max-time 30 http://127.0.0.1:8081/api/v1/health" && echo

echo "deploy ok: ${PUBLIC_URL}"
echo "magicart on :80/:443 untouched. API remains ${CNCFLOW_WORKER_URL:-https://cncflow-api.yzcaijunjie6095.workers.dev}"
