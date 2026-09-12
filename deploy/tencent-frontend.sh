#!/usr/bin/env bash
set -euo pipefail

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly DIST_DIR="${REPO_ROOT}/frontend/dist"
readonly SOURCE_CONF="${REPO_ROOT}/deploy/nginx-cncflow-tencent.conf"
readonly TARGET_CONF="/etc/nginx/conf.d/cncflow-tencent.conf"
readonly WWW_ROOT="/var/www/cncflow"
readonly PUBLIC_URL="http://43.129.175.172:8081/"

if ((EUID != 0)); then
    echo "error: run this script as root (for example, sudo $0)" >&2
    exit 1
fi

if [[ ! -f "${DIST_DIR}/index.html" ]]; then
    echo "error: ${DIST_DIR}/index.html not found" >&2
    echo "build first: cd frontend && VITE_BASE=/ VITE_API_URL= npm run build" >&2
    exit 1
fi

for command in nginx rsync; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "error: required command not found: ${command}" >&2
        exit 1
    fi
done

install -d -m 0755 "${WWW_ROOT}"
rsync -a --delete "${DIST_DIR}/" "${WWW_ROOT}/"
chown -R root:root "${WWW_ROOT}"

previous_conf="$(mktemp)"
had_previous_conf=false
if [[ -f "${TARGET_CONF}" ]]; then
    cp -p "${TARGET_CONF}" "${previous_conf}"
    had_previous_conf=true
fi

install -m 0644 "${SOURCE_CONF}" "${TARGET_CONF}"
if ! nginx -t; then
    if [[ "${had_previous_conf}" == true ]]; then
        cp -p "${previous_conf}" "${TARGET_CONF}"
    else
        rm -f "${TARGET_CONF}"
    fi
    rm -f "${previous_conf}"
    echo "error: nginx config test failed; restored previous config" >&2
    exit 1
fi
rm -f "${previous_conf}"

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl reload nginx
else
    nginx -s reload
fi

echo "Tencent frontend deployed: ${PUBLIC_URL}"
