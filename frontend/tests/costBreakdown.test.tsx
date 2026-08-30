import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import {
  CostBreakdown,
  costValue,
  fixtureCost,
  HANDBOOK_PENDING_NOTE,
  millTimeRows,
  programmingDrawerValues,
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
  inspect: 0,
  toolwear: 0,
  scrap: 0,
}

function costRow(label: string) {
  const row = screen.getByText(label).parentElement
  assert.ok(row)
  return within(row)
}

function programmingQuote(programmingTime: number, programmingCost: number) {
  return {
    program_count: 1,
    programming_time: programmingTime,
    t_programming: programmingTime,
    programming_cost: programmingCost,
    programming_cost_per_piece: programmingCost,
    programming_cost_detail: [{
      programming_time: programmingTime,
      machine_axes: 3,
      hourly_rate: 40,
      batch_size: 1,
      is_repeat_order: programmingCost === 0,
      cost_before_batch: programmingCost,
      cost_per_piece: programmingCost,
    }],
    equipment: {
      model: "VMC850E",
      axes: 3,
      hourly_rate: 120,
    },
    fixture: {
      setup_count: 1,
    },
  }
}

test("Ø8 刀具损耗显示两位小数且其他冻结成本行不回归", () => {
  render(
    <CostBreakdown
      quote={{
        ...programmingQuote(93, 62),
        fixture: {
          is_fixture_needed: false,
          fixture_material_cost: 0,
          fixture_processing_cost: 0,
        },
      }}
      uiCost={{
        ...uiCost,
        material: 3.25,
        machining: 1.39,
        setup: 210,
        programming: 62,
        inspect: 60,
        toolwear: 0.15,
        scrap: 16.84,
      }}
      quoteSummary={quoteSummary}
    />,
  )

  assert.ok(costRow("原材料").getByText("¥3.25"))
  assert.ok(costRow("加工工时").getByText("¥211.39"))
  assert.ok(costRow("装夹").getByText("¥0.00"))
  assert.ok(costRow("编程").getByText("¥62"))
  assert.equal(screen.queryByText("¥60.00"), null)
  assert.ok(costRow("检测").getByText("¥0.00"))
  assert.ok(costRow("刀具损耗").getByText("¥0.00"))
  assert.ok(costRow("不良损耗").getByText("¥0.00"))
  assert.equal(screen.getAllByText(HANDBOOK_PENDING_NOTE).length, 3)
})

test("点击检测行打开费用抽屉并标明知识库暂无规则", () => {
  render(
    <CostBreakdown
      quote={programmingQuote(93, 62)}
      uiCost={{ ...uiCost, inspect: 60 }}
      quoteSummary={quoteSummary}
    />,
  )

  const inspectRow = screen.getByRole("button", { name: /检测/ })
  assert.ok(within(inspectRow).getByText("¥0.00"))
  fireEvent.click(inspectRow)

  const drawer = screen.getByRole("dialog", { name: "检测费用" })
  assert.deepEqual(
    Array.from(drawer.querySelectorAll("dt"), element => element.textContent),
    ["单价", "计费", "费用"],
  )
  assert.deepEqual(
    Array.from(drawer.querySelectorAll("dd"), element => element.textContent),
    ["0 ¥/件", "1 件", "0.00"],
  )
  assert.ok(within(drawer).getByText(HANDBOOK_PENDING_NOTE))
})

test("点击不良损耗行打开费用抽屉并标明知识库暂无规则", () => {
  render(
    <CostBreakdown
      quote={{
        ...programmingQuote(93, 62),
        scrap_cost_breakdown: {
          slider: "标准",
          material_group: "易切",
          scrap_rate: 0.05,
          base: 279.11,
          scrap_fee: 16.84,
          note: HANDBOOK_PENDING_NOTE,
        },
      }}
      uiCost={{ ...uiCost, scrap: 16.84 }}
      quoteSummary={quoteSummary}
    />,
  )

  const scrapRow = screen.getByRole("button", { name: /不良损耗/ })
  assert.ok(within(scrapRow).getByText("¥0.00"))
  fireEvent.click(scrapRow)

  const drawer = screen.getByRole("dialog", { name: "不良损耗费用" })
  assert.deepEqual(
    Array.from(drawer.querySelectorAll("dt"), element => element.textContent),
    ["滑轴档", "材料组", "报废率", "计费基数", "不良损耗"],
  )
  assert.deepEqual(
    Array.from(drawer.querySelectorAll("dd"), element => element.textContent),
    ["标准", "易切", "5%", "279.11", "0.00"],
  )
  assert.ok(within(drawer).getByText(HANDBOOK_PENDING_NOTE))
})

test("387101 显示夹具材料加加工费用且刀耗不良检测为 0", () => {
  render(
    <CostBreakdown
      quote={{
        fixture: {
          is_fixture_needed: true,
          fixture_material: "铝合金",
          fixture_count: 1,
          fixture_block_L: 103.5,
          fixture_block_W: 103.5,
          fixture_block_H: 47,
          fixture_material_cost: 40.78,
          fixture_processing_cost: 1.72,
        },
      }}
      uiCost={{
        ...uiCost,
        machining: 101.4,
        setup: 210,
        inspect: 60,
        toolwear: 0.24,
        scrap: 69.63,
      }}
      quoteSummary={quoteSummary}
    />,
  )

  assert.ok(costRow("加工工时").getByText("¥311.40"))
  const fixtureRow = screen.getByRole("button", { name: /装夹/ })
  assert.ok(within(fixtureRow).getByText("¥42.50"))
  assert.ok(costRow("检测").getByText("¥0.00"))
  assert.ok(costRow("刀具损耗").getByText("¥0.00"))
  assert.ok(costRow("不良损耗").getByText("¥0.00"))
  fireEvent.click(fixtureRow)
  assert.ok(
    within(screen.getByRole("dialog", { name: "夹具1" })).getByText("1.72"),
  )
})

test("NUC 截图三行检测刀耗不良必须显示 0.00", () => {
  render(
    <CostBreakdown
      quote={{
        ...programmingQuote(36, 24),
        fixture: {
          is_fixture_needed: false,
          fixture_material_cost: 0,
          fixture_processing_cost: 0,
        },
      }}
      uiCost={{
        ...uiCost,
        material: 13.86,
        machining: 54.23,
        setup: 0,
        programming: 24,
        inspect: 60,
        toolwear: 0.28,
        scrap: 7.60,
      }}
      quoteSummary={{ amount: 105.90, cost: 92.09 }}
    />,
  )

  assert.ok(costRow("原材料").getByText("¥13.86"))
  assert.ok(costRow("加工工时").getByText("¥54.23"))
  assert.ok(costRow("装夹").getByText("¥0.00"))
  assert.ok(costRow("编程").getByText("¥24"))
  assert.ok(costRow("检测").getByText("¥0.00"))
  assert.ok(costRow("刀具损耗").getByText("¥0.00"))
  assert.ok(costRow("不良损耗").getByText("¥0.00"))
  assert.equal(screen.queryByText("¥60.00"), null)
  assert.equal(screen.queryByText("¥0.28"), null)
  assert.equal(screen.queryByText("¥7.60"), null)
})

test("零刀具损耗与零材料费一致显示两位小数", () => {
  render(
    <CostBreakdown
      quote={{}}
      uiCost={{ ...uiCost, material: 0, toolwear: 0 }}
      quoteSummary={quoteSummary}
    />,
  )

  assert.ok(costRow("原材料").getByText("¥0.00"))
  assert.ok(costRow("刀具损耗").getByText("¥0.00"))
})

test("点击编程行打开 Ø8 编程费用抽屉并按冻结顺序显示现网字段", () => {
  const quote = programmingQuote(93, 62)
  render(
    <CostBreakdown
      quote={quote}
      uiCost={uiCost}
      quoteSummary={quoteSummary}
    />,
  )

  const programmingRow = screen.getByRole("button", { name: /编程/ })
  assert.ok(within(programmingRow).getByText("¥62"))
  fireEvent.click(programmingRow)

  const drawer = screen.getByRole("dialog", { name: "编程费用" })
  assert.deepEqual(
    Array.from(drawer.querySelectorAll("dt"), element => element.textContent),
    [
      "编程数量：",
      "编程总工时：",
      "设备名称：",
      "编程单价：",
      "编程总费用：",
      "单件分摊成本：",
    ],
  )
  assert.deepEqual(
    Array.from(drawer.querySelectorAll("dd"), element => element.textContent),
    ["1（程序）", "93 min", "VMC850E", "¥40/h", "¥62", "¥62"],
  )
  assert.equal(within(drawer).queryByText("¥120/h"), null)
  assert.equal(quote.program_count, quote.fixture.setup_count)
  assert.equal(
    quote.programming_time * quote.programming_cost_detail[0].hourly_rate / 60,
    quote.programming_cost,
  )
})

for (const [sample, programmingTime, programmingCost] of [
  ["开口槽", 103, 68.67],
  ["M8", 93, 62],
] as const) {
  test(`${sample} 编程抽屉字段保持 #98 pin`, () => {
    const values = programmingDrawerValues(
      programmingQuote(programmingTime, programmingCost),
    )

    assert.deepEqual(values, {
      count: "1（程序）",
      time: `${programmingTime} min`,
      equipment: "VMC850E",
      hourlyRate: "¥40/h",
      totalCost: `¥${programmingCost}`,
      perPieceCost: `¥${programmingCost}`,
    })
  })
}

test("翻单仍显示 93 min，编程行、总费用和单件分摊均为 0", () => {
  const quote = programmingQuote(93, 0)
  render(
    <CostBreakdown
      quote={quote}
      uiCost={{ ...uiCost, programming: 0 }}
      quoteSummary={quoteSummary}
    />,
  )

  const programmingRow = screen.getByRole("button", { name: /编程/ })
  assert.ok(within(programmingRow).getByText("¥0"))
  fireEvent.click(programmingRow)

  const drawer = screen.getByRole("dialog", { name: "编程费用" })
  assert.ok(within(drawer).getByText("93 min"))
  assert.equal(within(drawer).getAllByText("¥0").length, 2)
})

function millStep(partial: Record<string, unknown>) {
  const time = (partial.time || {}) as Record<string, unknown>
  return {
    name: partial.name,
    process: partial.process,
    sku: partial.sku,
    formula: partial.formula,
    n: partial.n,
    f: partial.f,
    cut: partial.cut,
    passes: partial.passes,
    time: {
      formula: time.formula ?? partial.formula,
      n: time.n ?? partial.n,
      f: time.f ?? partial.f,
      cut: time.cut ?? partial.cut,
      passes: time.passes ?? partial.passes,
      t_cut: time.t_cut,
    },
  }
}

function operationFields(section: HTMLElement, needle: string) {
  const card = Array.from(section.querySelectorAll("dl")).find((dl) =>
    Array.from(dl.querySelectorAll("dd"), dd => dd.textContent).includes(needle),
  )
  assert.ok(card, needle)
  return Object.fromEntries(
    Array.from(card.querySelectorAll("div"), (row) => [
      row.querySelector("dt")?.textContent,
      row.querySelector("dd")?.textContent,
    ]),
  )
}

function assertMillTime(
  fields: Record<string, string | undefined>,
  expected: Record<string, string>,
) {
  for (const [key, value] of Object.entries(expected)) {
    assert.equal(fields[key], value, key)
  }
}

test("millTimeRows 只读 time.t_cut，倒角缺 n/f 则省略", () => {
  assert.deepEqual(
    millTimeRows(millStep({
      formula: "t=cut*passes/f",
      n: 7957.7,
      f: 2864.78,
      cut: 14.4,
      passes: 1,
      time: { t_cut: 0.0069 },
    })),
    [
      ["formula", "t=cut*passes/f"],
      ["n", "7957.7"],
      ["f", "2864.78"],
      ["cut", "14.4"],
      ["passes", "1"],
      ["t切削", "0.0069"],
    ],
  )
  assert.deepEqual(
    millTimeRows({
      formula: "t=cut*passes/f",
      n: null,
      f: null,
      cut: 56,
      passes: 1,
      t_cut: 9.99,
      time: { t_cut: 0.2182 },
    }),
    [
      ["formula", "t=cut*passes/f"],
      ["cut", "56"],
      ["passes", "1"],
      ["t切削", "0.2182"],
    ],
  )
})

test("四工步中间量冻结：面 TK-028 / 钻 TK-003 / 槽 TK-022 / 攻牙 TK-033", () => {
  assert.deepEqual(
    Object.fromEntries(millTimeRows(millStep({
      sku: "TK-028",
      formula: "t=cut*passes/f",
      cut: 85.714,
      time: { t_cut: 0.136 },
    }))),
    {
      formula: "t=cut*passes/f",
      cut: "85.714",
      t切削: "0.136",
    },
  )
  assert.deepEqual(
    Object.fromEntries(millTimeRows(millStep({
      sku: "TK-003",
      cut: 14.4,
      time: { t_cut: 0.0069 },
    }))),
    {
      cut: "14.4",
      t切削: "0.0069",
    },
  )
  assert.deepEqual(
    Object.fromEntries(millTimeRows(millStep({
      sku: "TK-022",
      cut: 95.238,
      passes: 8,
      time: { t_cut: 0.1847 },
    }))),
    {
      cut: "95.238",
      passes: "8",
      t切削: "0.1847",
    },
  )
  assert.deepEqual(
    Object.fromEntries(millTimeRows(millStep({
      sku: "TK-033",
      formula: "t=cut/(n*P)",
      n: 1000,
      time: { t_cut: 0.0096 },
    }))),
    {
      formula: "t=cut/(n*P)",
      n: "1000",
      t切削: "0.0096",
    },
  )
})

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
  const process_sequence = [
    millStep({
      name: "粗铣",
      process: "rough_face",
      sku: "TK-028",
      formula: "t=cut*passes/f",
      n: 3183.1,
      f: 1145.91,
      cut: 85.714,
      passes: 1,
      time: { t_cut: 0.136 },
    }),
    millStep({
      name: "钻孔",
      process: "drill",
      sku: "TK-003",
      formula: "t=cut*passes/f",
      n: 7957.7,
      f: 2864.78,
      cut: 14.4,
      passes: 1,
      time: { t_cut: 0.0069 },
    }),
    millStep({
      name: "倒角",
      process: "chamfer",
      sku: "TK-036",
      formula: "t=cut*passes/f",
      n: null,
      f: null,
      cut: 56,
      passes: 1,
      time: { t_cut: 0.2182 },
    }),
  ]
  render(
    <CostBreakdown
      quote={{ labor_cost_breakdown: labor, process_sequence }}
      uiCost={{ ...uiCost, machining: 1.39, setup: 210 }}
      quoteSummary={quoteSummary}
    />,
  )

  const machiningRow = screen.getByRole("button", { name: /加工工时/ })
  assert.ok(within(machiningRow).getByText("¥211.39"))
  fireEvent.click(machiningRow)

  const drawer = screen.getByRole("dialog", { name: "加工费用" })
  const changeover = within(drawer)
    .getByRole("heading", { name: "装夹工时" })
    .closest("section")!
  assert.deepEqual(
    Array.from(changeover.querySelectorAll("dt"), element => element.textContent),
    ["装夹时长", "加工设备", "设备费率", "装夹工时费"],
  )
  const hole = within(drawer).getByRole("heading", { name: "孔 × 1" }).closest("section")!
  const face = within(drawer).getByRole("heading", { name: "面 × 1" }).closest("section")!
  for (const text of ["钻孔", "TK-003", "0.09", "¥0.18"]) {
    assert.ok(within(hole).getByText(text))
  }
  for (const text of ["粗铣", "TK-028", "0.22", "¥0.44", "倒角", "TK-036", "0.30", "¥0.60"]) {
    assert.ok(within(face).getByText(text))
  }
  assertMillTime(operationFields(hole, "钻孔"), {
    formula: "t=cut*passes/f",
    n: "7957.7",
    f: "2864.78",
    cut: "14.4",
    passes: "1",
    t切削: "0.0069",
  })
  assertMillTime(operationFields(face, "粗铣"), {
    formula: "t=cut*passes/f",
    n: "3183.1",
    f: "1145.91",
    cut: "85.714",
    passes: "1",
    t切削: "0.136",
  })
  const chamfer = operationFields(face, "倒角")
  assertMillTime(chamfer, {
    formula: "t=cut*passes/f",
    cut: "56",
    passes: "1",
    t切削: "0.2182",
  })
  assert.equal(chamfer.n, undefined)
  assert.equal(chamfer.f, undefined)
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
  assert.equal(labor.machining, 1.39)
})

test("加工费用抽屉显示开口槽粗铣 TK-022 中间量且加工工时保持 211.59", () => {
  const slotLabor = {
    machining: 1.59,
    setup: 210,
    total: 211.59,
    machining_total: 1.59,
    air_cut_and_tool_change_cost: 0.17,
    groups: [
      {
        feature_type: "slot",
        name: "槽",
        quantity: 1,
        operations: [{
          name: "粗铣",
          equipment_name: "VMC850E",
          tool_sku: "TK-022",
          minutes: 0.2681,
          hourly_rate: 120,
          cost: 0.54,
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
    changeover: { minutes: 5, equipment_name: "VMC850E", hourly_rate: 120, cost: 210 },
  }
  render(
    <CostBreakdown
      quote={{
        labor_cost_breakdown: slotLabor,
        process_sequence: [
          millStep({
            name: "粗铣",
            process: "rough_pocket",
            sku: "TK-022",
            formula: "t=cut*passes/f",
            n: 6366.2,
            f: 2291.83,
            cut: 95.238,
            passes: 8,
            time: { t_cut: 0.1847 },
          }),
          millStep({
            name: "粗铣",
            process: "rough_face",
            sku: "TK-028",
            formula: "t=cut*passes/f",
            n: 3183.1,
            f: 1145.91,
            cut: 85.714,
            passes: 1,
            time: { t_cut: 0.1364 },
          }),
          millStep({
            name: "倒角",
            process: "chamfer",
            sku: "TK-036",
            formula: "t=cut*passes/f",
            n: null,
            f: null,
            cut: 56,
            passes: 1,
            time: { t_cut: 0.2182 },
          }),
        ],
      }}
      uiCost={{ ...uiCost, machining: 1.59, setup: 210 }}
      quoteSummary={quoteSummary}
    />,
  )

  assert.ok(costRow("加工工时").getByText("¥211.59"))
  fireEvent.click(screen.getByRole("button", { name: /加工工时/ }))
  const slotDrawer = screen.getByRole("dialog", { name: "加工费用" })
  const slot = within(slotDrawer).getByRole("heading", { name: "槽 × 1" }).closest("section")!
  assertMillTime(operationFields(slot, "TK-022"), {
    formula: "t=cut*passes/f",
    n: "6366.2",
    f: "2291.83",
    cut: "95.238",
    passes: "8",
    t切削: "0.1847",
  })
  assert.equal(slotLabor.machining, 1.59)
})

test("加工费用抽屉显示 M8 攻牙 TK-033 中间量且加工工时保持 211.19", () => {
  const tapLabor = {
    machining: 1.19,
    setup: 210,
    total: 211.19,
    machining_total: 1.19,
    air_cut_and_tool_change_cost: 0.17,
    groups: [
      {
        feature_type: "thread",
        name: "螺纹",
        quantity: 1,
        operations: [{
          name: "攻牙",
          equipment_name: "VMC850E",
          tool_sku: "TK-033",
          minutes: 0.093,
          hourly_rate: 120,
          cost: 0.19,
        }],
      },
    ],
    changeover: { minutes: 5, equipment_name: "VMC850E", hourly_rate: 120, cost: 210 },
  }
  render(
    <CostBreakdown
      quote={{
        labor_cost_breakdown: tapLabor,
        process_sequence: [
          millStep({
            name: "攻牙",
            process: "tap",
            sku: "TK-033",
            formula: "t=cut/(n*P)",
            n: 1000,
            f: 180,
            cut: 12,
            passes: 1,
            time: { t_cut: 0.0096 },
          }),
        ],
      }}
      uiCost={{ ...uiCost, machining: 1.19, setup: 210 }}
      quoteSummary={quoteSummary}
    />,
  )
  assert.ok(costRow("加工工时").getByText("¥211.19"))
  fireEvent.click(screen.getByRole("button", { name: /加工工时/ }))
  const tapDrawer = screen.getByRole("dialog", { name: "加工费用" })
  const thread = within(tapDrawer).getByRole("heading", { name: "螺纹 × 1" }).closest("section")!
  assertMillTime(operationFields(thread, "攻牙"), {
    formula: "t=cut/(n*P)",
    n: "1000",
    f: "180",
    cut: "12",
    passes: "1",
    t切削: "0.0096",
  })
  assert.equal(tapLabor.machining, 1.19)
})

test("加工工时行冻结金额不因抽屉中间量回归", () => {
  for (const [sample, total] of [
    ["Ø8", 211.39],
    ["开口槽", 211.59],
    ["M8", 211.19],
    ["NUC", 54.23],
    ["台阶", 214.18],
  ] as const) {
    const view = render(
      <CostBreakdown
        quote={{}}
        uiCost={{ ...uiCost, machining: total, setup: 0 }}
        quoteSummary={quoteSummary}
      />,
    )
    assert.ok(costRow("加工工时").getByText(`¥${total.toFixed(2)}`), sample)
    view.unmount()
  }
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
