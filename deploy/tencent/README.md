# Tencent static frontend (dual publish)

Static Vite build only. Flask / LLM / parser / R2 stay on Cloudflare.

## Public URL

**http://43.129.175.172:8081/**

| Port | Owner | Action |
| --- | --- | --- |
| 80 / 443 | magicart | do not bind, reload-only nginx |
| 8080 | occupied | do not bind |
| **8081** | cncflow static | this vhost |

`HostAlias tencent` → `root@43.129.175.172`.

```
# ~/.ssh/config
Host tencent
  HostName 43.129.175.172
  User root
```

## Layout

- nginx root: `/var/www/cncflow` (`VITE_BASE=/` → `/assets/...`)
- site: `/etc/nginx/conf.d/cncflow-static.conf`
- `/api/` → `https://cncflow-api.yzcaijunjie6095.workers.dev/api/` (same-origin)

Tencent security group: open **TCP 8081**. HTTP only (443 is magicart).

## Publish

From a box that can `ssh tencent`:

```bash
./deploy/tencent/check.sh
./deploy/tencent/publish.sh
```

`publish.sh` builds `frontend` with `VITE_BASE=/` and **unset** `VITE_API_URL` so the browser calls `/api/v1` on :8081.

```bash
# dist already built for Tencent (no VITE_API_URL)
./deploy/tencent/publish.sh --skip-build

# update files only (nginx already installed)
./deploy/tencent/publish.sh --skip-nginx
```

GitHub Actions (after Pages) runs the same script when `TENCENT_SSH_PRIVATE_KEY` is set. Secret is a repo secret, never committed.

Open firewall + first install once; later pushes are rsync + `nginx -t` + `reload`.

## CORS fallback (if you rsync the Pages dist)

Pages bakes `VITE_API_URL=https://cncflow-api.yzcaijunjie6095.workers.dev`. That dist talks to the Worker cross-origin; nginx `/api` is unused.

Tighten Worker secret (comma-separated, no repo file):

```
CNCFLOW_CORS_ORIGINS=https://cncflow.pages.dev,http://43.129.175.172:8081
```

`*` still works. Same-origin proxy is preferred.

## Out of scope

Do not copy `deploy/deploy.sh` / `deploy/nginx-cncflow.conf` (those proxy to local Flask on the other VPS). Do not change quote pins.
