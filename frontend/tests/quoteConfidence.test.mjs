import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
  new URL("../src/quoteConfidence.ts", import.meta.url),
  "utf8",
)
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const {
  confidenceColumns,
  DIMENSION_LABEL,
  EMPTY_DEDUCTION_TEXT,
  formatDeduction,
  liveConfidenceValue,
} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)

function item(dimension, deduction = 5, reason = `${dimension} 原因`) {
  return {
    rule_id: `${dimension}-1`,
    dimension,
    deduction,
    reason,
  }
}

test("D1–D9 按冻结映射进入四个可信度列", () => {
  const columns = confidenceColumns([
    item("D1", 1),
    item("D2", 1),
    item("D3", 1),
    item("D4", 1),
    item("D5", 1),
    item("D6", 1),
    item("D7", 1),
    item("D8", 1),
    item("D9", 1),
  ])

  assert.deepEqual(columns.map(({ key, label, score, deductions }) => ({
    key,
    label,
    score,
    dimensions: deductions.map((deduction) => deduction.dimension),
  })), [
    { key: "drawing", label: "图纸识别", score: 99, dimensions: ["D9"] },
    { key: "process", label: "工艺可加工性", score: 96, dimensions: ["D1", "D2", "D5", "D6"] },
    { key: "factory", label: "工厂资源匹配", score: 99, dimensions: ["D4"] },
    { key: "cost", label: "成本数据完整性", score: 97, dimensions: ["D3", "D7", "D8"] },
  ])
  assert.equal(
    columns.flatMap((column) => column.deductions)
      .every(({ deduction }) => /^−\d+(?:\.\d+)?$/.test(formatDeduction(deduction))),
    true,
  )
})

test("Ø8 的两条 D1 各扣 5，工艺列与现有总置信度均为 90", () => {
  const columns = confidenceColumns([
    item("D1", 5, "工步 1 rough_face 工时低于下限"),
    item("D1", 5, "工步 2 drill 工时低于下限"),
  ])
  const process = columns.find((column) => column.key === "process")

  assert.equal(process.score, 90)
  assert.equal(process.deductions.length, 2)
  assert.deepEqual(process.deductions.map(({ deduction }) => formatDeduction(deduction)), ["−5", "−5"])
  assert.equal(liveConfidenceValue(90), 90)
  assert.deepEqual(
    columns.filter((column) => column.key !== "process").map(({ score, deductions }) => ({
      score,
      count: deductions.length,
    })),
    [
      { score: 100, count: 0 },
      { score: 100, count: 0 },
      { score: 100, count: 0 },
    ],
  )
})

test("2D 缺字段归图纸，刀具可达性归工艺", () => {
  const columns = confidenceColumns([
    item("D5", 5, "2D图纸未提供局部公差"),
    item("D9", 5, "精加工区域刀具可达性不足"),
  ])

  assert.deepEqual(
    columns.find((column) => column.key === "drawing").deductions.map(({ reason }) => reason),
    ["2D图纸未提供局部公差"],
  )
  assert.deepEqual(
    columns.find((column) => column.key === "process").deductions.map(({ reason }) => reason),
    ["精加工区域刀具可达性不足"],
  )
})

test("列分使用扣分绝对值并在 0 截断", () => {
  const process = confidenceColumns([
    item("D1", -60),
    item("D2", 50),
  ]).find((column) => column.key === "process")

  assert.equal(process.score, 0)
  assert.deepEqual(process.deductions.map(({ deduction }) => deduction), [60, 50])
})

test("标签和无数值条目不生成表格行，空列使用冻结空态", () => {
  const columns = confidenceColumns([
    "禁止给客户",
    { dimension: "D1", reason: "超出常规边界" },
    { tag: "设备不匹配" },
  ])

  assert.equal(columns.every((column) => column.deductions.length === 0), true)
  assert.equal(columns.every((column) => column.score === 100), true)
  assert.equal(EMPTY_DEDUCTION_TEXT, "无扣分项")
})

test("保留 PR #94 冻结的 D 标签", () => {
  assert.deepEqual({
    D3: DIMENSION_LABEL.D3,
    D6: DIMENSION_LABEL.D6,
    D7: DIMENSION_LABEL.D7,
    D8: DIMENSION_LABEL.D8,
  }, {
    D3: "成本比例",
    D6: "工序顺序",
    D7: "材料成本",
    D8: "数据一致性",
  })
})
