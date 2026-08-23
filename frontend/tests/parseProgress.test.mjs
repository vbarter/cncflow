import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const source = await readFile(
  new URL("../src/parseProgress.ts", import.meta.url),
  "utf8",
)

test("六步标签按冻结顺序声明", () => {
  const labels = [
    "读模型",
    "特征公差",
    "工艺 SETUP",
    "匹配设备刀具",
    "算工时成本",
    "综合报价",
  ]
  let previous = -1
  for (const label of labels) {
    const position = source.indexOf(`"${label}"`)
    assert.ok(position > previous, `${label} 未按冻结顺序声明`)
    previous = position
  }
})

test("失败空态使用冻结文案", () => {
  assert.match(source, /title: "解析失败"/)
  assert.match(source, /body: "模型未能完成解析，请检查 STEP 后重试"/)
  assert.match(source, /action: "重试"/)
})
