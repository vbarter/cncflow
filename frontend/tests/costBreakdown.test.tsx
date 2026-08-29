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

test("点击加工工时行打开 Ø8 加工费用抽屉并与现网 labor 对账", () => {
  const labor = {
    machining: 1.39,
    setup: 210,
    total: 211.39,
    operation_cost: 1.22,
    air_cut_and_tool_change_cost: 0.17,
    machining_total: 1.39,
    groups: [
      {
        feature_type: "hole",
        name: "孔",
        quantity: 1,
        operations: [{
          name: "钻孔",
          equipment_name: "VMC850E",
          tool_sku: "TK-003",
          minutes: 0.0902,
          hourly_rate: 120,
          cost: 0.18,
        }],
      },
      {
        feature_type: "face",
        name: "面",
        quantity: 1,
        operations: [
          {
            name: "粗铣",
            equipment_name: "VMC850E",
            tool_sku: "TK-028",
            minutes: 0.2193,
            hourly_rate: 120,
            cost: 0.44,
          },
          {
            name: "倒角",
            equipment_name: "VMC850E",
            tool_sku: "TK-036",
            minutes: 0.3016,
            hourly_rate: 120,
            cost: 0.60,
          },
        ],
      },
    ],
    changeover: {
      minutes: 5,
      equipment_name: "VMC850E",
      hourly_rate: 120,
      labor_cost: 10,
      machine_setup_cost: 200,
      cost: 210,
    },
  }
  render(
    <CostBreakdown
      quote={{ labor_cost_breakdown: labor }}
      uiCost={{ ...uiCost, machining: 1.39, setup: 210 }}
      quoteSummary={quoteSummary}
    />,
  )

  const machiningRow = screen.getByRole("button", { name: /加工工时/ })
  assert.ok(within(machiningRow).getByText("¥211.39"))
  fireEvent.click(machiningRow)

  const drawer = screen.getByRole("dialog", { name: "加工费用" })
  const hole = within(drawer).getByRole("heading", { name: "孔 × 1" }).closest("section")!
  const face = within(drawer).getByRole("heading", { name: "面 × 1" }).closest("section")!
  for (const text of ["钻孔", "TK-003", "0.09", "¥0.18"]) {
    assert.ok(within(hole).getByText(text))
  }
  for (const text of ["粗铣", "TK-028", "0.22", "¥0.44", "倒角", "TK-036", "0.30", "¥0.60"]) {
    assert.ok(within(face).getByText(text))
  }
  assert.ok(within(drawer).getByText("含空程 / 换刀 ¥0.17"))
  for (const text of ["5.00 min", "¥120/h", "¥210.00", "调机 ¥200.00 + 工时 ¥10.00"]) {
    assert.ok(within(drawer).getByText(text))
  }
  assert.ok(within(drawer).getByText("¥211.39"))
  assert.equal(costValue({ labor_cost_breakdown: labor }, {
    ...uiCost,
    machining: 1.39,
    setup: 210,
  }, "machining"), 211.39)
})

test("点击原材料行打开材料费用抽屉并显示 Ø8 冻结明细", () => {
  render(
    <CostBreakdown
      quote={{
        material_cost_breakdown: {
          density_g_cm3: 2.7,
          blank_price_per_kg: 30,
          scrap_price_per_kg: 16,
          blank_volume_mm3: 86016,
          blank_weight_kg: 0.2322,
          part_volume_mm3: 56.997,
          part_weight_kg: 0.00015,
          scrap_volume_mm3: 85959.003,
          scrap_weight_kg: 0.2321,
          blank_cost: 6.97,
          scrap_recycle_cost: 3.71,
          net_material_cost: 3.25,
        },
      }}
      uiCost={{ ...uiCost, material: 3.25 }}
      quoteSummary={quoteSummary}
    />,
  )

  const materialRow = screen.getByRole("button", { name: /原材料/ })
  assert.ok(within(materialRow).getByText("¥3.25"))
  fireEvent.click(materialRow)

  const drawer = screen.getByRole("dialog", { name: "材料费用" })
  for (const heading of ["基础信息", "动态参数", "计算过程"]) {
    assert.ok(within(drawer).getByRole("heading", { name: heading }))
  }
  for (const value of [
    "2.7 g/cm³",
    "¥30/kg",
    "¥16/kg",
    "86016 mm³ / 0.2322 kg",
    "56.997 mm³ / 0.00015 kg",
    "85959.003 mm³ / 0.2321 kg",
    "¥6.97",
    "¥3.71",
    "¥3.25",
  ]) {
    assert.ok(within(drawer).getByText(value))
  }
  assert.ok(within(drawer).getByText("净材料费 = 毛坯费 − 回收费 = 原材料行金额"))
})

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
    fixture_material_cost: 40.82,
    fixture_processing_cost: 0,
  }
  const quote = { fixture }

  assert.equal(fixtureCost(fixture), 40.82)
  assert.equal(costValue(quote, uiCost, "fixture"), 40.82)
  assert.equal(costValue(quote, uiCost, "machining"), 25)

  render(
    <CostBreakdown
      quote={quote}
      uiCost={uiCost}
      quoteSummary={quoteSummary}
    />,
  )

  const fixtureRow = screen.getByRole("button", { name: /装夹/ })
  assert.ok(within(fixtureRow).getByText("¥40.82"))
  fireEvent.click(fixtureRow)

  const drawer = screen.getByRole("dialog", { name: "夹具1" })
  for (const text of [
    "1 套",
    "铝合金",
    "120×100×42 mm（504000 mm³）",
    "40.82",
    "0.00",
  ]) {
    assert.ok(within(drawer).getByText(text))
  }
})
