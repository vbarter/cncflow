#!/usr/bin/env bash
# Local sanity checks for Tencent static dual-publish. No SSH, no secrets.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CONF="$HERE/nginx-cncflow-static.conf"
PUBLISH="$HERE/publish.sh"

fail() { echo "check failed: $*" >&2; exit 1; }

[ -f "$CONF" ] || fail "missing $CONF"
[ -x "$PUBLISH" ] || fail "publish.sh must be executable"
bash -n "$PUBLISH"
bash -n "$HERE/check.sh"

# Port freeze: magicart owns 80/443; 8080 is occupied.
if grep -E '^[[:space:]]*listen[[:space:]]+(80|443|8080)\b' "$CONF"; then
  fail "nginx must not listen on 80/443/8080"
fi
grep -q 'listen 8081' "$CONF" || fail "expected listen 8081"

grep -q 'proxy_pass https://cncflow-api.yzcaijunjie6095.workers.dev/api/' "$CONF" \
  || fail "expected /api reverse proxy to Cloudflare Worker"
grep -q 'root /var/www/cncflow' "$CONF" || fail "expected static root /var/www/cncflow"
grep -q 'proxy_buffering off' "$CONF" || fail "chat/SSE needs proxy_buffering off"

# No Flask/systemd migration leftovers in this vhost
if grep -Eiq '127\.0\.0\.1:5001|cncflow\.service|proxy_pass http://127' "$CONF"; then
  fail "static vhost must not proxy to local Flask"
fi

# Secrets never in repo (skip this checker — it names the tokens it forbids)
if grep -RE --exclude='check.sh' \
    -e 'BEGIN (OPENSSH|RSA) PRIVATE KEY' \
    -e 'BEGIN PRIVATE KEY' \
    -e 'TUZI_API_KEY=.+' \
    -e 'CLOUDFLARE_API_TOKEN=.+' \
    "$HERE"; then
  fail "secret material in deploy/tencent"
fi

# Pages workflow still publishes to Cloudflare; Tencent is additive.
WF="$ROOT/.github/workflows/cloudflare.yml"
grep -q 'npx wrangler pages deploy ../frontend/dist --project-name=cncflow' "$WF" \
  || fail "Cloudflare Pages publish step missing"
grep -q 'Publish static frontend to Tencent' "$WF" \
  || fail "optional Tencent job missing"
grep -q 'needs: pages' "$WF" || fail "Tencent job must run after Pages"

# Optional nginx -t if nginx is installed
if command -v nginx >/dev/null; then
  WRAP="$(mktemp -d)"
  mkdir -p "$WRAP/www" "$WRAP/logs" "$WRAP/conf"
  cat > "$WRAP/nginx.conf" <<EOF
worker_processes 1;
error_log $WRAP/logs/error.log;
pid $WRAP/nginx.pid;
events { worker_connections 64; }
http {
    access_log $WRAP/logs/access.log;
    client_body_temp_path $WRAP/tmp 1 2;
    proxy_temp_path $WRAP/tmp 1 2;
    fastcgi_temp_path $WRAP/tmp 1 2;
    uwsgi_temp_path $WRAP/tmp 1 2;
    scgi_temp_path $WRAP/tmp 1 2;
    include $CONF;
}
EOF
  mkdir -p "$WRAP/tmp"
  nginx -t -c "$WRAP/nginx.conf" -p "$WRAP" \
    || fail "nginx -t rejected $CONF"
  rm -rf "$WRAP"
  echo "nginx -t ok"
fi

echo "tencent dual-publish checks ok"
echo "public URL: http://43.129.175.172:8081/"
