# cncflow

孔特征加工评估服务：可加工性、工艺链、刀具需求/SKU、加工参数、材料知识与已审核工艺案例。

## API

- `POST /api/v1/process-plan`：生成孔加工方案。兼容材料族名称，也支持 `material_code`、`strategy` 和可选 `machine_profile`。
- `GET /api/v1/materials`：查询规范化材料目录，支持 `q`、`family`、`planning_status`。
- `GET /api/v1/health`：健康检查。
- `POST /api/v1/parse-jobs`：上传 STP/PDF 并创建异步解析任务。STEP 特征主路径是 tu-zi `gpt-6-astra`（`TUZI_API_KEY`）；`CNCFLOW_FEATURE_PARSER=geometry` 回退 CadQuery 插件。
- `GET /api/v1/parse-jobs/{job_id}`：查询解析进度及制造特征候选。
- `POST /api/v1/parse-jobs/{job_id}/confirm`：确认孔特征并生成加工方案。

访问 `/cncflow/` 可使用黑白单页上传界面。前端构建产物由 Flask 托管，CAD/PDF解析由独立 Worker 执行。

外部材料知识只作为带来源的参考层，不会覆盖 `backend/cncflow_core/rules/` 中的已验证规则。
工艺案例通过 `python -m data.import_process_cases cases.json` 受控导入，只有 `verified` 案例参与相似检索。

生产环境不会自动灌入模拟 SKU；如需演示，显式设置 `CNCFLOW_SEED_MOCK_TOOLS=1`。

## Cloudflare + Tencent（前端双发）

生产目标是 Pages（前端）+ Container（Flask 与解析进程）+ R2（STP/PDF 与 SQLite 检查点）。细节见 `cloudflare/README.md`。

| 前端 | URL | 构建 |
| --- | --- | --- |
| Cloudflare Pages | https://cncflow.pages.dev | `VITE_BASE=/` + `VITE_API_URL` → Worker |
| Tencent VPS | **http://43.129.175.172:8081/** | `VITE_BASE=/`，同域 `/api` → nginx → Worker |

API 只在 Cloudflare Worker：`https://cncflow-api.yzcaijunjie6095.workers.dev`。腾讯机**只跑 Vite 静态文件 + nginx**，不迁 Flask / LLM / parser / R2。80/443 是 magicart、8080 已占用，所以独立听 **8081**。

Pages 工作流不变；main 推送后可选 rsync（secret `TENCENT_SSH_PRIVATE_KEY`）。没配 key 时用 HostAlias：

```bash
./deploy/tencent/publish.sh   # ssh tencent → root@43.129.175.172
```

跑本见 `deploy/tencent/README.md`。旧 VPS Flask 发布（`deploy/deploy.sh`）仍可用，与腾讯静态站无关。
