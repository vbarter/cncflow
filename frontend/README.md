# cncflow frontend

Vite + React + TypeScript + Tailwind CSS 单页应用。

## 发布目标

- Cloudflare Pages 是主站，`.github/workflows/cloudflare.yml` 在 `main` 推送时继续构建并发布。
- Tencent VPS 是静态前端试点：`http://43.129.175.172:8081/`。
- 两处前端都使用现有 API Worker；Tencent 不运行 Flask、LLM 或 STEP parser。

Cloudflare Pages 构建：

```bash
npm ci
VITE_BASE=/ \
VITE_API_URL=https://cncflow-api.yzcaijunjie6095.workers.dev \
npm run build
```

Tencent 构建必须使用根路径和空的 API origin：

```bash
npm ci
VITE_BASE=/ VITE_API_URL= npm run build
sudo ../deploy/tencent-frontend.sh
```

空的 `VITE_API_URL` 会让 `src/api.ts` 使用 `BASE_URL=/`，最终请求
`/api/v1/...`。浏览器因此请求同源的 `43.129.175.172:8081/api/...`，
再由独立的 nginx 8081 server block 转发到 API Worker；不需要修改
Worker 的 CORS allowlist。

部署脚本将 `frontend/dist` 同步到 `/var/www/cncflow`，安装
`deploy/nginx-cncflow-tencent.conf`，执行 `nginx -t` 后 reload。现有
magicart（80/443）、巴小卡（8080）和海外 VPS 配置不受影响。
