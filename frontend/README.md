# cncflow frontend

Vite + React + TypeScript + Tailwind CSS 单页应用。Hash router。

| 宿主 | `VITE_BASE` | API |
| --- | --- | --- |
| 本地 / 旧 VPS Flask | `/cncflow/`（默认） | `/cncflow/api/v1` |
| Cloudflare Pages | `/` | `VITE_API_URL` → Worker |
| Tencent nginx `:8081` | `/` | 同域 `/api/v1`（nginx 反代 Worker） |

```bash
npm ci
npm run build
# Tencent / Pages 根路径：
VITE_BASE=/ npm run build
```

腾讯发布：`./deploy/tencent/publish.sh` → http://43.129.175.172:8081/
