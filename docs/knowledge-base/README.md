# CNC 知识库（chat jail）

本目录是公开报价助手的手册入口。阈值与判定规则**不写在这里**，一律以 `backend/cncflow_core/rules/` 的 YAML 为准（见 `prompts/README.md`）。

- 手册：`CNC知识库使用手册-v5.1.md`
- 外圆报价冻结规则：[外圆特征加工报价逻辑结构化规则文档](外圆特征加工报价逻辑结构化规则文档.md)
- 倒角/圆角报价待审冻规则：[倒角/圆角特征加工报价逻辑结构化规则文档](倒角圆角特征加工报价逻辑结构化规则文档.md)
- 规则：`backend/cncflow_core/rules/**`
- 实现：`backend/cncflow_core/**`、`frontend/src/**`

chat agent 的 cwd 是 jail，只能 `read` / 只读 `bash` 这些树，不能改报价数字、工厂配置或任何文件。
