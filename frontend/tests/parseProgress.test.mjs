import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import ts from "typescript"

const source = await readFile(
  new URL("../src/parseProgress.ts", import.meta.url),
  "utf8",
)
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const {
  PARSE_FAILURE,
  PARSE_STEPS,
  parseStepFromJobs,
} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)

test("六步标签按冻结顺序输出", () => {
  assert.deepEqual(PARSE_STEPS, [
    "读模型",
    "特征公差",
    "工艺 SETUP",
    "匹配设备刀具",
    "算工时成本",
    "综合报价",
  ])
})

test("失败空态使用冻结文案", () => {
  assert.deepEqual(PARSE_FAILURE, {
    title: "解析失败",
    body: "模型未能完成解析，请检查 STEP 后重试",
    action: "重试",
  })
})

test("parse-job 状态只按最慢零件推进解析阶段", () => {
  assert.equal(parseStepFromJobs([
    { status: "running", stage: "geometry_parse", progress: 20 },
  ]), 0)
  assert.equal(parseStepFromJobs([
    { status: "running", stage: "pdf_drawing", progress: 65 },
  ]), 1)
  assert.equal(parseStepFromJobs([
    { status: "needs_review", stage: "review", progress: 100 },
    { status: "running", stage: "geometry_parse", progress: 20 },
  ]), 0)
  assert.equal(parseStepFromJobs([
    { status: "needs_review", stage: "review", progress: 100 },
  ]), 2)
})
