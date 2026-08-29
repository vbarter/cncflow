import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { PartDetail } from "../src/pages/PartDetail"

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
})
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
  MutationObserver: dom.window.MutationObserver,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: dom.window.navigator,
})

const { cleanup, render, screen } = await import("@testing-library/react")
const originalFetch = globalThis.fetch

afterEach(() => {
  cleanup()
  globalThis.fetch = originalFetch
})

test("AI 报价决策栏按冻结顺序堆叠六列，并保留 Ø8 实时 pin", async () => {
  const part = {
    id: "part-o8",
    inquiry_id: "inquiry-1",
    name: "Ø8",
    material_code: "6061",
    qty: 1,
    status: "quoted",
    mesh: { available: false },
    parsed_features: [],
    quote: {
      quote: {
        amount: 731,
        cost: 636,
        margin: 13.04,
        hours: 0.1,
      },
      ui_cost: {},
      risk: { level: "low", tags: [] },
      deductions: [
        { rule_id: "D1-1", dimension: "D1", deduction: 5, reason: "粗加工工时低于下限" },
        { rule_id: "D1-2", dimension: "D1", deduction: 5, reason: "钻孔工时低于下限" },
      ],
      process_sequence: [],
      suggested_days: 2,
      confidence: 90,
    },
  }
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => part,
  }) as Response

  render(<PartDetail id={part.id} go={() => {}} />)

  const header = await screen.findByText("01 AI QUOTE DECISION")
  const decision = header.closest("section")
  assert.ok(decision)

  assert.deepEqual(
    Array.from(decision.querySelectorAll("dt"), element => element.textContent),
    [
      "单件报价",
      "单件成本",
      "毛利率",
      "加工时间",
      "建议交期",
      "工艺风险 · 置信度",
    ],
  )

  const values = Array.from(decision.querySelectorAll("dd"))
  assert.equal(values.length, 6)
  assert.match(values[0].className, /\btext-2xl\b/)
  for (const value of values.slice(1)) {
    assert.match(value.className, /\btext-base\b/)
    assert.doesNotMatch(value.className, /\btext-2xl\b/)
  }
  assert.deepEqual(values.map(value => value.textContent), [
    "¥731",
    "¥636",
    "13.04%",
    "0.1h",
    "2 天",
    "2项 · 90",
  ])
  assert.match(values[5].querySelector("span")?.className || "", /\btext-red-300\b/)
  assert.ok(screen.getByRole("button", { name: "确认本零件报价" }))
})
