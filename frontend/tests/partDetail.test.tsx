import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { PartQuoteDecision } from "../src/components/PartQuoteDecision"

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

afterEach(cleanup)

test("AI 报价决策栏按冻结顺序堆叠六列，并保留 Ø8 实时 pin", () => {
  render(
    <PartQuoteDecision
      recommend="建议接单"
      quote="¥731"
      cost="¥636"
      margin="13.04%"
      machiningTime="0.1h"
      suggestedDelivery="2 天"
      riskCount={2}
      confidence={90}
      confirmAction={<button type="button">确认本零件报价</button>}
    />,
  )

  const header = screen.getByText("01 AI QUOTE DECISION")
  const decision = header.closest("section")
  assert.ok(decision)

  const decisionClasses = [
    decision.className,
    ...Array.from(
      decision.querySelectorAll<HTMLElement>("[class]"),
      element => element.className,
    ),
  ].join(" ")
  assert.doesNotMatch(decisionClasses, /\boverflow-x-auto\b/)
  assert.ok(!decisionClasses.includes("min-w-[720px]"))

  const metrics = decision.querySelector("dl")
  assert.ok(metrics)
  assert.match(metrics.className, /\bw-full\b/)
  assert.match(metrics.className, /\bgrid-cols-3\b/)
  assert.match(metrics.className, /\blg:grid-cols-6\b/)
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
  const confirmButton = screen.getByRole("button", { name: "确认本零件报价" })
  assert.ok(confirmButton)
  assert.equal(metrics.contains(confirmButton), false)
})
