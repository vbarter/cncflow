# prompts — SOP prompt 资产

本目录存放注入 Agent system prompt 的 SOP 流程文本（markdown），本期只占位。

约定：

- `system.md`：角色定义 + 输出规范
- `sop/*.md`：每条 SOP 一个自包含文件（触发条件 → 步骤 → 调用哪个接口/命令 → 输出格式），小节之间不互相引用
- **SOP 只写流程和接口调用方式，不写任何阈值/判定规则**——规则一律在 `backend/cncflow_core/rules/` 的 YAML 中，由规则引擎确定性执行
- 将来切换到 skill 方案时，每个 SOP 文件原样迁为 SKILL.md
