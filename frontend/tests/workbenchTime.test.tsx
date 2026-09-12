import assert from "node:assert/strict"
import test from "node:test"
import {
  formatShanghaiTimestamp,
  sortInquiriesByCreatedAt,
} from "../src/pages/Workbench"

test("报价工作台将无时区 API 时间按 UTC 解析并显示为上海时间", () => {
  assert.equal(formatShanghaiTimestamp("2026-09-12 10:17:03"), "09-12 18:17")
  assert.equal(formatShanghaiTimestamp("2026-09-12 16:20:00"), "09-13 00:20")
  assert.equal(formatShanghaiTimestamp("invalid"), "—")
})

test("报价工作台按创建时间升降序排列，缺失时间始终置底", () => {
  const items = [
    { id: "middle", created_at: "2026-09-12 10:17:03" },
    { id: "missing" },
    { id: "newest", created_at: "2026-09-12 12:00:00" },
    { id: "oldest", created_at: "2026-09-11 23:00:00" },
  ]

  assert.deepEqual(
    sortInquiriesByCreatedAt(items, "desc").map(item => item.id),
    ["newest", "middle", "oldest", "missing"],
  )
  assert.deepEqual(
    sortInquiriesByCreatedAt(items, "asc").map(item => item.id),
    ["oldest", "middle", "newest", "missing"],
  )
  assert.deepEqual(items.map(item => item.id), ["middle", "missing", "newest", "oldest"])
})
