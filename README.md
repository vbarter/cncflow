# cncflow

孔特征加工评估服务：可加工性、工艺链、刀具需求/SKU、加工参数、材料知识与已审核工艺案例。

## API

- `POST /api/v1/process-plan`：生成孔加工方案。兼容材料族名称，也支持 `material_code`、`strategy` 和可选 `machine_profile`。
- `GET /api/v1/materials`：查询规范化材料目录，支持 `q`、`family`、`planning_status`。
- `GET /api/v1/health`：健康检查。

外部材料知识只作为带来源的参考层，不会覆盖 `backend/cncflow_core/rules/` 中的已验证规则。
工艺案例通过 `python -m data.import_process_cases cases.json` 受控导入，只有 `verified` 案例参与相似检索。

生产环境不会自动灌入模拟 SKU；如需演示，显式设置 `CNCFLOW_SEED_MOCK_TOOLS=1`。
