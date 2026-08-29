import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const source = await readFile(
  new URL("../src/pages/FactoryConfig.tsx", import.meta.url),
  "utf8",
)

test("材料价格表显示冻结单位且不再显示回收率", () => {
  assert.match(source, /<th>密度 g\/cm³<\/th>/)
  assert.match(source, /<th>单价 ¥\/kg<\/th>/)
  assert.match(source, /<th>回收价 ¥\/kg<\/th>/)
  assert.doesNotMatch(source, /回收率|recycle_rate/)
})
