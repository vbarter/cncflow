# CNC 知识库使用手册 v5.1

cncflow 自动报价的十五阶段流水线。本手册只写阶段、代码路径和门禁语义。

**阈值不写在手册里。** 数字边界在 `backend/cncflow_core/rules/**/*.yaml`，由规则引擎执行。SOP / 本手册禁止复制 YAML 里的判定常数。

chat 只解释，不算价、不改数。检测 / 刀耗 / 不良在独立 Word 落地前恒为 0，禁止发明公式。

---

## 总览：十五阶段

报价入口：`POST /api/v1/quotes` → `backend/cncflow_core/quoting/engine.py` 的 `quote()`。

| 阶段 | 名称 | 代码 | 规则 |
| --- | --- | --- | --- |
| ① | 特征 | `backend/cncflow_core/features/*/pipeline.py`、`geometry/` | 各 feature YAML |
| ② | 工艺路线 | `features/hole/process_chain.py` 等 | `rules/*/process_chain.yaml` |
| ③ | 夹具 | `features/fixture/pipeline.py` | `rules/fixture/materials.yaml` |
| ④ | 工序排序 | `quoting/sequence.py` | — |
| ⑤ | 刀具 | `engine._diameter_selection`、`common/sku_match.py` | `rules/hole/tool_attrs.yaml` |
| ⑥ | 切削参数 | `quoting/slider.py`、`common/params_calc.py` | `rules/common/cutting_params.yaml` |
| ⑦ | 工时 | `quoting/hole_time.py`、`quoting/mill_time.py` | 工时上下限在 time 模块 |
| ⑧ | 防错校验 | `engine._validation` | 工步 `t_min`/`t_max` |
| ⑨ | 编程工时 | `quoting/programming.py` `calculate_time` | Word v3 常数在该文件 |
| ⑩ | 人工（加工+装夹） | `engine.py` ⑩ 段 | D9-4 空路线清零 |
| ⑪ | 编程成本 | `quoting/programming.py` `calculate_cost` | 费率表 / 默认轴费率 |
| ⑫ | 体积 | `quoting/volume.py` | 棒/板余量在该文件 |
| ⑬ | 材料费 | `engine._price` + volume | 工厂材料目录 |
| ⑭ | 夹具成本 | `features/fixture/pipeline.py` `_fixture_spec` | 0824 平口钳优先 |
| ⑮ | D1–D9 风险 | `quoting/risk_dimensions.py` | D9 硬门禁，不阻断出价 |

UI 成本栏：`ui_cost` = 材料 / 加工 / 装夹(setup) / 夹具 / 编程 / 检测 / 刀耗 / 不良。后三项 `HANDBOOK_PENDING_COST = 0`。

---

## ① 特征

`engine.PIPELINES` 按 `feature.type` 分发：

| type | pipeline |
| --- | --- |
| hole | `features/hole/pipeline.py` |
| face | `features/face/pipeline.py` |
| pocket / slot | `features/pocket/pipeline.py` |
| thread | `features/thread/pipeline.py` |
| surface | `features/surface/pipeline.py` |
| step | `features/step/pipeline.py` |

几何识别在 `backend/cncflow_core/geometry/`（STEP 插件）。报价吃的是确认后的 feature 列表，不是 chat。

去重：`quoting/dedup.py`（孔吸收、台阶面吸收、同孔工步合并、倒角合并）。

---

## ② 工艺路线（孔工艺链）

这是业务抽「孔工艺链怎么排」的主入口。

**实现：** `backend/cncflow_core/features/hole/process_chain.py` 的 `generate_chain()`  
**规则：** `backend/cncflow_core/rules/hole/process_chain.yaml`  
**顺序冻结：** 点钻 → 基础钻孔/镗削 → 精加工（F01–F09 只选一族）→ 螺纹（T01–T03 只选一个）→ 修底 → 倒角。

读取 YAML 用 `common/rule_loader.py`。问阈值时 `read` 该 YAML，不要背数字。

### 孔链怎么走

1. **超大孔**：直径超过 `large_hole.min_d` → 主工序 `rough_bore`，不再钻。精加工仍走 F01–F09。
2. **点钻 Step2**：倾斜/曲面、小孔、高精度、易跑偏材料（见 `spot_drill_triggers`）→ 第一道 `spot_drill`。
3. **主钻孔只选一道**
   - 微孔（`< micro_hole_max_d`）→ `micro_hole`（EDM / 超高速），禁止再镗铰
   - 极限深孔（`H/D > gun_drill_max_hd`）→ `special_hole`，禁止回退枪钻
   - 枪钻区间 → `gun_drill`
   - 否则 G81 / G83（`H/D ≥ g83_min_hd`）；大直径浅孔可 `u_drill`
4. **精加工 F01–F09**（`_select_finishing`）：互斥单选。默认 IT/Ra 组合可以没有精加工。磨削优先于切削精加工。
5. **螺纹 T01–T03**：无螺纹不加。否则攻牙或螺纹铣二选一（直径 / 不锈钢 / 深螺纹，见 `thread`）。
6. **修底**：盲孔平底 → `flat_bottom_mill`，插在螺纹后、倒角前。
7. **倒角**：`chamfer_always`。通孔入口+出口两道，盲孔一道。报价引擎稍后会 `dedup.merge_chamfers` 合成显示。

其它特征的路线：

- 面 / 槽 / 台阶 / 螺纹：各 `rules/*/process_chain.yaml` + 对应 pipeline
- 曲面：手补工时，常无 `process_sequence`（见 ⑩ + D9-4）

空 `process_sequence` 不是 chat 能补的。那是 ② 没产出可报价工步，⑩ 必须把加工人工打成 0。

---

## ③ 夹具

`features/fixture/pipeline.py`：F1–F5 类型 + 装夹次数 + 是否可加工。

- 方形默认平口钳 / 压板；轴/盘三爪；异形或淬硬钢专用夹具
- 三轴悬伸/曲面孔、超 Z → `is_machinable=false`，仍出价并打风险
- 装夹时间：`TIMES` × 材料系数 × 重量系数；铸锻焊 +5 min

---

## ④ 工序排序

`quoting/sequence.py` `sort_steps()`：

- 先按夹具组，再粗 → 半精 → 精，倒角永远组内最后
- 粗：槽/型腔 → 台阶 → 面 → 孔/螺纹
- 精：面 → 孔 → 槽 → 台阶 → 螺纹
- 人工改序：`quoting/process_edits.py`，每次倒置 +0.5 min

D6 查同一装夹组内「精不得早于粗、倒角必须最后」。

---

## ⑤ 刀具

- 孔钻 / 槽铣 / 螺纹底孔钻与丝锥：库存刀径**全等优先**，否则最近在库 SKU +「刀径非全等，需工艺确认」（`engine._uses_exact_diameter_policy`）
- 面铣保持原 SKU 规则
- 属性：`rules/hole/tool_attrs.yaml`
- 生产环境不自动灌模拟 SKU；演示才 `CNCFLOW_SEED_MOCK_TOOLS=1`

M8 攻牙冻结 SKU 在报价测试里钉死，chat 不要改。

---

## ⑥ 切削参数

两层，不要混：

1. **滑轴倍率** `quoting/slider.py`：钳位 × 材料组 → Vc/fz/ap 与 setup/toolchg/rapid 时间倍率。淬硬钢、微孔、深孔、超光面会把钳位往保守夹。
2. **绝对参数表** `rules/common/cutting_params.yaml`：给 process-plan / RAG 用。报价工时主路径用 `hole_time._vc_fz` / mill_time 查表 × 滑轴倍率。

`n = min(1000·Vc/(πd), max_rpm)`；攻牙再封顶 1000 rpm。转速不够乘 `slowdown`。

---

## ⑦ 工时

- 孔：`quoting/hole_time.py` — `t = cut·passes/f`，攻牙 `t = cut/(n·P)`
- 铣（面/槽/螺纹/台阶）：`quoting/mill_time.py` — 切削长度由面积或轮廓推
- 每步 `t_step = t_cut + t_tool`（换刀秒/60）
- 曲面：`manual_hours`，不走 DIFF_MIN 冒充切削

工时上下限与「低于下限 / 需人工复核」在 time 模块 `_bounds` / `_flag`。倒角无表则不进 D1。

---

## ⑧ 防错校验

`engine._validation(seq)`：只收集 `status != ok` 的工步（`t_min`/`t_max`）。**不含** D1–D9 的 `rule_id`。九维风险是 ⑮。

---

## ⑨ 编程工时

`quoting/programming.py` `calculate_time`：

`(T_FIXED + Σ t_base·难度·自由曲面系数 + 程序数·(T_POST+T_DEBUG)) · 轴系数`

无选中特征 → 0。`setup_count` 必须 > 0。翻单不影响工时，影响 ⑪ 的钱。

---

## ⑩ 人工（加工 + 装夹工时栏）

UI「加工工时」= `ui.machining + ui.setup`。

- `machining` = 切削费 + 换刀费 + 空程费
- `setup` = 装夹时间费 + 设备开机/setup 摊销

**D9-4 硬门禁（空工艺路线）：**

`engine.py`：若 `process_sequence` 为空，切削分钟只认曲面手补；手补也为 0 时，**换刀 / 空程 / 装夹时间 / setup 摊销全部清零**。禁止用 `DIFF_MIN` 或「默认 1 刀」冒充加工工时。

所以「缺少工艺路线时加工工时为什么是 0」= ② 没有可报价工步 + ⑩ 清零。引 `engine.py` 与本手册 ②⑩。

钉死验收（由 `backend/tests/test_quote_engine.py` 等保证，**不是 chat 的职责**）：

- Ø8 加工 211.39 / 材料 5.72 / 编程 93 min · 62
- 开口槽 211.59
- M8 211.19 · TK-033
- NUC 材料 13.86 / 加工+装夹 54.23
- 台阶 214.18
- 检测 / 刀耗 / 不良恒 0
- 空 `process_sequence`（D9-4）加工工时 0

chat 不得重算、不得改这些数。

---

## ⑪ 编程成本

`calculate_cost`：`工时 × 编程小时费率 / 60 / 批量`。翻单整段为 0。缺费率时按 3/4/5 轴默认。

---

## ⑫ 体积

`quoting/volume.py`：

- 棒：按 D 分档余量；板：按厚分档余量
- `V_part` 优先 CAD（`v_part_cad`）；否则按轴/盘/板/箱体经验系数
- 面特征缺面积时，engine 可用 CAD 净面积补（通窗板）

---

## ⑬ 材料费

`净材料 = 毛坯重 × 单价 − 废料重 × 废料单价`。密度/单价来自工厂材料目录，缺省才走族默认。这是材料栏，不是「不良损耗」。

---

## ⑭ 夹具成本

`_fixture_spec`（0824）：

- 翻单、或「有夹持面 + 壁厚够 + 无倾斜 + 平面 + IT 够松 + 方向少」→ **不需要专用夹具**（平口钳路径），夹具费 0
- 否则做块：材料费 + 把夹具块当面/孔/M8 螺纹走现有工时链的加工费
- 夹具费进 `ui.fixture`，与 ⑩ 的装夹工时栏分开

---

## ⑮ D1–D9 风险（D9 硬门禁）

`quoting/risk_dimensions.py`。置信度 = `100 − Σ deduction`。D9 任一命中：`customer_forbidden`、风险至少 high。

| 维 | 含义 | 典型 rule |
| --- | --- | --- |
| D1 | 工时低于下限 | D1-1（倒角不参与） |
| D2 | MRR 超出边界 | D2-1 |
| D3 | 材料/加工/夹具占报价过高 | D3-1/2/3 |
| D4 | 设备不匹配 | D4-1 |
| D5 | n 或 f ≤ 0 | D5-1 |
| D6 | 精先于粗 / 倒角不在最后 | D6-1 |
| D7 | 净材料 ≤0 或高于报价 | D7-1 |
| D8 | 设备字段缺或切削工时与路线不一致 | D8-1 |
| D9 | 关键字段缺失，**仍出价** | D9-1 材料；D9-2 外形；D9-3 未选特征；**D9-4 无可报价工艺路线** |

D9-4 与 ⑩ 联动：缺路线扣分 **并且** 加工人工为 0。

---

## 检测 / 刀耗 / 不良

知识库无独立 Word。`engine.HANDBOOK_PENDING_COST = 0`。不读工厂 `inspect_fee`，不套 `cut_hours*15` 或 `base*scrap_rate`。UI 与 `cost_items` 的 INSPECT / TOOLWEAR / SCRAP 恒 0。chat 禁止编公式。

---

## 给助手的读法

1. 先 `read docs/knowledge-base/CNC知识库使用手册-v5.1.md` 对阶段。
2. 问阈值 → `read backend/cncflow_core/rules/...yaml`，不要默写。
3. 问「代码怎么报价」→ `read backend/cncflow_core/quoting/engine.py` 及对应模块。
4. 问孔工艺链 → 本手册 ② + `process_chain.py` + `rules/hole/process_chain.yaml`。
5. 问 D9 空路线工时为 0 → 本手册 ②⑩ + `engine.py`。
6. 不确定就说不确定。数字以引擎和测试钉为准。
