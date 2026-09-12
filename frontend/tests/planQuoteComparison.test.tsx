import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { PlanQuoteComparison } from "../src/components/PlanQuoteComparison"

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

test("renders blank decision and at least two engine comparison rows", () => {
  render(<PlanQuoteComparison quote={{
    blank: {
      label: "板料",
      envelope_mm: { length: 80, width: 60, height: 12 },
      suggested_stock_size: { display: "85 × 65 × 16 mm" },
      rule: "厚宽比≤0.25",
    },
    candidates: [
      { id: "user-plan", source: "user" },
      { id: "rule-efficient", source: "rule" },
    ],
    comparison: [
      {
        plan_id: "user-plan",
        label: "用户给定",
        machine: "3轴立式加工中心",
        setup_count: 2,
        machining_time_hours: 1.2,
        machining_cost: 30,
        total_cost: 100,
        quoted_amount: 115,
      },
      {
        plan_id: "rule-efficient",
        label: "少装夹方案",
        machine: "4轴立式加工中心",
        setup_count: 1,
        machining_time_hours: 0.8,
        machining_cost: 25,
        total_cost: 95,
        quoted_amount: 109.25,
      },
    ],
  }} />)

  assert.ok(screen.getByText("板料 · 85 × 65 × 16 mm"))
  assert.ok(screen.getAllByText("用户给定").length >= 1)
  assert.ok(screen.getByText("少装夹方案"))
  assert.equal(screen.getAllByRole("row").length, 3)
})
