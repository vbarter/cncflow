# cncflow Cloudflare

Pages hosts the React UI. A Worker proxies HTTP into one Container running Flask plus the CadQuery parser. R2 holds STP/PDF and the SQLite checkpoint.

Flask stays Flask. SQLite stays SQLite (not D1).

Container disk is ephemeral. The process restores `/data/cncflow.db` from object `db/cncflow.db` in bucket `cncflow-files` on boot, then snapshots every 60 seconds and on SIGTERM.

Uploads keep a local content-addressed cache. `storage_path` becomes `r2://cncflow-files/<aa>/<sha256>` when R2 env is set.

`max_instances` is 1 (SQLite single writer). `min_instances` is 1 so the parser keeps polling.

Required Worker secrets: R2 account, access key, secret, bucket; `CNCFLOW_CORS_ORIGINS` for the Pages origin; optional `VISION_API_KEY` for drawing OCR via api.tu-zi.com.

Frontend production build uses `VITE_BASE=/` and `VITE_API_URL` pointing at the `cncflow-api` Worker origin. The Cloudflare workflow publishes `frontend/dist` to Pages project `cncflow` on every main push. VPS SSH publish remains as a fallback.

CORS is applied at the Worker (OPTIONS 204 + ACAO on proxied responses). `CNCFLOW_CORS_ORIGINS` defaults to `*`; Flask `_install_cors` is defense in depth only.
