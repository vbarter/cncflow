import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import {
  CostBreakdown,
  costValue,
  fixtureCost,
} from "../src/components/CostBreakdown"

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
})
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  navigator: dom.window.navigator,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
  MutationObserver: dom.window.MutationObserver,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})

const { cleanup, fireEvent, render, screen, within } = await import(
  "@testing-library/react"
)

afterEach(cleanup)

const quoteSummary = { amount: 200, cost: 100 }
const uiCost = {
  material: 10,
  machining: 20,
  setup: 5,
  fixture: 999,
  programming: 62,
  inspect: 1,
  toolwear: 2,
  scrap: 3,
}

test("点击装夹行打开平口钳空态抽屉", () => {
  render(
    <CostBreakdown
      quote={{
        fixture: {
          is_fixture_needed: false,
          fixture_material: "-",
          fixture_count: 0,
          fixture_block_L: 0,
          fixture_block_W: 0,
          fixture_block_H: 0,
          fixture_material_cost: 0,
          fixture_processing_cost: 0,
        },
      }}
      uiCost={uiCost}
      quoteSummary={quoteSummary}
    />,
  )

  const fixtureRow = screen.getByRole("button", { name: /装夹/ })
  assert.ok(within(fixtureRow).getByText("¥0.00"))
  fireEvent.click(fixtureRow)

  const drawer = screen.getByRole("dialog", { name: "夹具1" })
  for (const text of [
    "0 套",
    "平口钳",
    "0×0×0 mm（0 mm³）",
    "0.00",
  ]) {
    assert.ok(within(drawer).getAllByText(text).length)
  }
  assert.ok(within(drawer).getByText("夹具材料费用："))
  assert.ok(within(drawer).getByText("夹具加工费用："))
})

test("IT6 装夹行和抽屉只使用夹具材料、加工费用", () => {
  const fixture = {
    is_fixture_needed: true,
    fixture_material: "铝合金",
    fixture_count: 1,
    fixture_block_L: 120,
    fixture_block_W: 100,
    fixture_block_H: 42,
    fixture_material_cost: 29.94,
    fixture_processing_cost: 0,
  }
  const quote = { fixture }

  assert.equal(fixtureCost(fixture), 29.94)
  assert.equal(costValue(quote, uiCost, "fixture"), 29.94)
  assert.equal(costValue(quote, uiCost, "machining"), 25)

  render(
    <CostBreakdown
      quote={quote}
      uiCost={uiCost}
      quoteSummary={quoteSummary}
    />,
  )

  const fixtureRow = screen.getByRole("button", { name: /装夹/ })
  assert.ok(within(fixtureRow).getByText("¥29.94"))
  fireEvent.click(fixtureRow)

  const drawer = screen.getByRole("dialog", { name: "夹具1" })
  for (const text of [
    "1 套",
    "铝合金",
    "120×100×42 mm（504000 mm³）",
    "29.94",
    "0.00",
  ]) {
    assert.ok(within(drawer).getByText(text))
  }
})
