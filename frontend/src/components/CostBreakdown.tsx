import React, { useEffect, useState } from "react"
import { Card } from "./ui"

const COST_ROWS = [
  ["material", "原材料"],
  ["machining", "加工工时"],
  ["fixture", "装夹"],
  ["programming", "编程"],
  ["inspect", "检测"],
  ["toolwear", "刀具损耗"],
  ["scrap", "不良损耗"],
] as const

export const HANDBOOK_PENDING_NOTE = "知识库暂无规则，待独立 Word 后再计"
const HANDBOOK_PENDING_KEYS = new Set(["inspect", "toolwear", "scrap"])

function number(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function yen(value: unknown) {
  if (value == null || value === "") return "—"
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed.toFixed(0) : "—"
}

function dimension(value: unknown) {
  const parsed = number(value)
  return Number.isInteger(parsed) ? String(parsed) : String(parsed)
}

function decimal(value: unknown, maximumFractionDigits: number) {
  if (value == null || value === "") return "—"
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return "—"
  return parsed.toFixed(maximumFractionDigits).replace(/\.?0+$/, "")
}

export function fixtureCost(fixture: any) {
  return number(fixture?.fixture_material_cost) + number(fixture?.fixture_processing_cost)
}

export function costValue(quote: any, uiCost: any, key: string) {
  if (key === "fixture") return fixtureCost(quote?.fixture)
  if (key === "machining") {
    return number(uiCost?.machining) + number(uiCost?.setup)
  }
  return number(uiCost?.[key])
}

export function fixtureDrawerValues(fixture: any) {
  if (!fixture?.is_fixture_needed) {
    return {
      count: "0 套",
      material: "平口钳",
      volume: "0×0×0 mm（0 mm³）",
      materialCost: "0.00",
      processingCost: "0.00",
    }
  }

  const length = number(fixture.fixture_block_L)
  const width = number(fixture.fixture_block_W)
  const height = number(fixture.fixture_block_H)
  const volume = length * width * height
  return {
    count: `${number(fixture.fixture_count)} 套`,
    material: fixture.fixture_material || "—",
    volume: `${dimension(length)}×${dimension(width)}×${dimension(height)} mm（${dimension(volume)} mm³）`,
    materialCost: number(fixture.fixture_material_cost).toFixed(2),
    processingCost: number(fixture.fixture_processing_cost).toFixed(2),
  }
}

export function materialDrawerValues(material: any) {
  const volumeWeight = (volume: unknown, weight: unknown) =>
    `${decimal(volume, 3)} mm³ / ${decimal(weight, 5)} kg`

  return {
    density: `${decimal(material?.density_g_cm3, 2)} g/cm³`,
    blankPrice: `¥${decimal(material?.blank_price_per_kg, 2)}/kg`,
    scrapPrice: `¥${decimal(material?.scrap_price_per_kg, 2)}/kg`,
    blank: volumeWeight(material?.blank_volume_mm3, material?.blank_weight_kg),
    part: volumeWeight(material?.part_volume_mm3, material?.part_weight_kg),
    scrap: volumeWeight(material?.scrap_volume_mm3, material?.scrap_weight_kg),
    blankCost: `¥${number(material?.blank_cost).toFixed(2)}`,
    scrapRecycleCost: `¥${number(material?.scrap_recycle_cost).toFixed(2)}`,
    netMaterialCost: `¥${number(material?.net_material_cost).toFixed(2)}`,
  }
}

function currency(value: unknown) {
  const formatted = decimal(value, 2)
  return formatted === "—" ? formatted : `¥${formatted}`
}

export function programmingDrawerValues(quote: any) {
  const costDetail = Array.isArray(quote?.programming_cost_detail)
    ? quote.programming_cost_detail[0]
    : undefined
  const programCount = quote?.program_count ?? quote?.fixture?.setup_count
  const programmingTime = quote?.programming_time ?? quote?.t_programming

  return {
    count: `${decimal(programCount, 4)}（程序）`,
    time: `${decimal(programmingTime, 4)} min`,
    equipment: quote?.equipment?.model || "—",
    hourlyRate: costDetail?.hourly_rate == null
      ? "—"
      : `${currency(costDetail.hourly_rate)}/h`,
    totalCost: currency(quote?.programming_cost),
    perPieceCost: currency(quote?.programming_cost_per_piece),
  }
}

export function inspectDrawerValues(inspectFee: unknown) {
  return {
    unitPrice: `${decimal(inspectFee, 2)} ¥/件`,
    billedQuantity: "1 件",
    fee: number(inspectFee).toFixed(2),
    note: HANDBOOK_PENDING_NOTE,
  }
}

export function scrapDrawerValues(scrap: any) {
  const rate = scrap?.scrap_rate

  return {
    slider: scrap?.slider || "—",
    materialGroup: scrap?.material_group || "—",
    scrapRate: rate == null || rate === ""
      ? "—"
      : `${decimal(number(rate) * 100, 2)}%`,
    base: number(scrap?.base).toFixed(2),
    scrapFee: number(scrap?.scrap_fee).toFixed(2),
    note: scrap?.note || HANDBOOK_PENDING_NOTE,
  }
}

export function matchMachiningStep(
  operation: any,
  sequence: any[],
  used: Set<number>,
) {
  if (!Array.isArray(sequence) || !sequence.length) return undefined
  const name = operation?.name
  const sku = operation?.tool_sku
  let fallback = -1
  for (let index = 0; index < sequence.length; index++) {
    if (used.has(index)) continue
    const step = sequence[index]
    const stepName = step?.name || step?.process
    const stepSku = step?.sku
    const nameHit = Boolean(name) && stepName === name
    const skuHit = Boolean(sku) && Boolean(stepSku) && stepSku === sku
    if (nameHit && skuHit) {
      used.add(index)
      return step
    }
    if (fallback < 0 && (skuHit || (nameHit && !sku))) fallback = index
  }
  if (fallback < 0) return undefined
  used.add(fallback)
  return sequence[fallback]
}

export function millTimeRows(source: any): [string, string][] {
  if (!source) return []
  const time = source.time || {}
  const formula = source.formula ?? time.formula
  const n = source.n ?? time.n ?? time.n_act
  const f = source.f ?? time.f
  const cut = source.cut ?? time.cut
  const passes = source.passes ?? time.passes
  const t = time.t_cut
  const rows: [string, string][] = []
  if (formula != null && formula !== "") rows.push(["formula", String(formula)])
  if (n != null && n !== "") rows.push(["n", decimal(n, 4)])
  if (f != null && f !== "") rows.push(["f", decimal(f, 4)])
  if (cut != null && cut !== "") rows.push(["cut", decimal(cut, 4)])
  if (passes != null && passes !== "") rows.push(["passes", decimal(passes, 0)])
  if (t != null && t !== "") rows.push(["t切削", decimal(t, 4)])
  return rows
}

function machiningOperationRows(operation: any, step: any) {
  return [
    ["工序名称", operation.name || "—"],
    ["设备名称", operation.equipment_name || "—"],
    ["刀具 SKU", operation.tool_sku || "—"],
    ["加工时长 (min)", number(operation.minutes).toFixed(2)],
    ["设备费率 (¥/h)", number(operation.hourly_rate).toFixed(0)],
    ["工序费用", `¥${number(operation.cost).toFixed(2)}`],
    ...millTimeRows(step || operation),
  ]
}

function MaterialDrawer({ material, onClose }: { material: any; onClose: () => void }) {
  const values = materialDrawerValues(material)

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [onClose])

  const blocks = [
    {
      title: "基础信息",
      rows: [
        ["材料密度", values.density],
        ["毛坯单价", values.blankPrice],
        ["废料回收单价", values.scrapPrice],
      ],
    },
    {
      title: "动态参数",
      rows: [
        ["毛坯体积 / 毛坯重量", values.blank],
        ["工件体积 / 工件重量", values.part],
        ["废料体积 / 废料重量", values.scrap],
      ],
    },
    {
      title: "计算过程",
      rows: [
        ["毛坯费用", values.blankCost],
        ["废料回收费用", values.scrapRecycleCost],
        ["工件最终材料费用 / 净材料费", values.netMaterialCost],
      ],
    },
  ]

  return <>
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-slate-950/30"
      aria-label="关闭材料费用明细"
      onClick={onClose}
    />
    <aside
      id="material-cost-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="material-cost-drawer-title"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <h2 id="material-cost-drawer-title" className="text-lg font-semibold">材料费用</h2>
        <button
          type="button"
          className="flex size-10 items-center justify-center rounded text-2xl text-slate-500 hover:bg-slate-100"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <div className="space-y-7 px-6 py-6 text-sm">
        {blocks.map((block) => (
          <section key={block.title} aria-labelledby={`material-${block.title}`}>
            <h3
              id={`material-${block.title}`}
              className="mb-3 font-medium text-slate-900"
            >
              {block.title}
            </h3>
            <dl className="divide-y divide-slate-100 rounded border border-slate-200">
              {block.rows.map(([label, value]) => (
                <div className="px-4 py-3" key={label}>
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="mt-1 font-mono text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
        <p className="rounded bg-slate-50 px-4 py-3 text-xs text-slate-500">
          净材料费 = 毛坯费 − 回收费 = 原材料行金额
        </p>
      </div>
    </aside>
  </>
}

function MachiningDrawer({
  labor,
  sequence,
  onClose,
}: {
  labor: any
  sequence: any[]
  onClose: () => void
}) {
  const groups = Array.isArray(labor?.groups) ? labor.groups : []
  const changeover = labor?.changeover || {}
  const usedSteps = new Set<number>()

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [onClose])

  return <>
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-slate-950/30"
      aria-label="关闭加工费用明细"
      onClick={onClose}
    />
    <aside
      id="machining-cost-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="machining-cost-drawer-title"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-xl overflow-y-auto bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <h2 id="machining-cost-drawer-title" className="text-lg font-semibold">加工费用</h2>
        <button
          type="button"
          className="flex size-10 items-center justify-center rounded text-2xl text-slate-500 hover:bg-slate-100"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <div className="space-y-7 px-6 py-6 text-sm">
        {groups.map((group: any) => (
          <section key={group.feature_type} aria-labelledby={`machining-${group.feature_type}`}>
            <h3
              id={`machining-${group.feature_type}`}
              className="mb-3 font-medium text-slate-900"
            >
              {group.name} × {number(group.quantity)}
            </h3>
            <div className="space-y-3">
              {(group.operations || []).map((operation: any, index: number) => (
                <dl
                  className="grid grid-cols-2 gap-x-4 gap-y-3 rounded border border-slate-200 px-4 py-3"
                  key={`${operation.name}-${operation.tool_sku}-${index}`}
                >
                  {machiningOperationRows(
                    operation,
                    matchMachiningStep(operation, sequence, usedSteps),
                  ).map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-xs text-slate-500">{label}</dt>
                      <dd className="mt-1 font-mono text-slate-900">{value}</dd>
                    </div>
                  ))}
                </dl>
              ))}
            </div>
          </section>
        ))}
        <section aria-labelledby="machining-subtotal">
          <h3 id="machining-subtotal" className="mb-3 font-medium text-slate-900">工序合计</h3>
          <div className="rounded border border-slate-200 px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">工序总费用</span>
              <span className="font-mono">¥{number(labor?.machining_total).toFixed(2)}</span>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              含空程 / 换刀 ¥{number(labor?.air_cut_and_tool_change_cost).toFixed(2)}
            </p>
          </div>
        </section>
        <section aria-labelledby="machining-changeover">
          <h3 id="machining-changeover" className="mb-3 font-medium text-slate-900">装夹工时</h3>
          <dl className="divide-y divide-slate-100 rounded border border-slate-200">
            {[
              ["装夹时长", `${number(changeover.minutes).toFixed(2)} min`],
              ["加工设备", changeover.equipment_name || "—"],
              ["设备费率", `¥${number(changeover.hourly_rate).toFixed(0)}/h`],
              ["装夹工时费", `¥${number(changeover.cost).toFixed(2)}`],
            ].map(([label, value]) => (
              <div className="flex items-center justify-between gap-4 px-4 py-3" key={label}>
                <dt className="text-slate-500">{label}</dt>
                <dd className="font-mono text-right text-slate-900">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-slate-500">
            调机 ¥{number(changeover.machine_setup_cost).toFixed(2)}
            {" + "}
            工时 ¥{number(changeover.labor_cost).toFixed(2)}
          </p>
        </section>
        <div className="flex items-center justify-between rounded bg-slate-900 px-4 py-4 text-white">
          <span className="font-medium">总计</span>
          <span className="font-mono text-lg">¥{number(labor?.total).toFixed(2)}</span>
        </div>
      </div>
    </aside>
  </>
}

function ProgrammingDrawer({ quote, onClose }: { quote: any; onClose: () => void }) {
  const values = programmingDrawerValues(quote)

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [onClose])

  const rows = [
    ["编程数量：", values.count],
    ["编程总工时：", values.time],
    ["设备名称：", values.equipment],
    ["编程单价：", values.hourlyRate],
    ["编程总费用：", values.totalCost],
    ["单件分摊成本：", values.perPieceCost],
  ]

  return <>
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-slate-950/30"
      aria-label="关闭编程费用明细"
      onClick={onClose}
    />
    <aside
      id="programming-cost-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="programming-cost-drawer-title"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <h2 id="programming-cost-drawer-title" className="text-lg font-semibold">编程费用</h2>
        <button
          type="button"
          className="flex size-10 items-center justify-center rounded text-2xl text-slate-500 hover:bg-slate-100"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <dl className="divide-y divide-slate-100 px-6 py-6 text-sm">
        {rows.map(([label, value]) => (
          <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0" key={label}>
            <dt className="text-slate-500">{label}</dt>
            <dd className="font-mono text-right text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  </>
}

function InspectDrawer({
  inspectFee,
  onClose,
}: {
  inspectFee: unknown
  onClose: () => void
}) {
  const values = inspectDrawerValues(inspectFee)

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [onClose])

  const rows = [
    ["单价", values.unitPrice],
    ["计费", values.billedQuantity],
    ["费用", values.fee],
  ]

  return <>
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-slate-950/30"
      aria-label="关闭检测费用明细"
      onClick={onClose}
    />
    <aside
      id="inspect-cost-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="inspect-cost-drawer-title"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <h2 id="inspect-cost-drawer-title" className="text-lg font-semibold">检测费用</h2>
        <button
          type="button"
          className="flex size-10 items-center justify-center rounded text-2xl text-slate-500 hover:bg-slate-100"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <dl className="divide-y divide-slate-100 px-6 py-6 text-sm">
        {rows.map(([label, value]) => (
          <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0" key={label}>
            <dt className="text-slate-500">{label}</dt>
            <dd className="font-mono text-right text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="px-6 pb-6 text-xs text-slate-500">{values.note}</p>
    </aside>
  </>
}

function ScrapDrawer({ scrap, onClose }: { scrap: any; onClose: () => void }) {
  const values = scrapDrawerValues(scrap)

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [onClose])

  const rows = [
    ["滑轴档", values.slider],
    ["材料组", values.materialGroup],
    ["报废率", values.scrapRate],
    ["计费基数", values.base],
    ["不良损耗", values.scrapFee],
  ]

  return <>
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-slate-950/30"
      aria-label="关闭不良损耗费用明细"
      onClick={onClose}
    />
    <aside
      id="scrap-cost-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="scrap-cost-drawer-title"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <h2 id="scrap-cost-drawer-title" className="text-lg font-semibold">不良损耗费用</h2>
        <button
          type="button"
          className="flex size-10 items-center justify-center rounded text-2xl text-slate-500 hover:bg-slate-100"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <dl className="divide-y divide-slate-100 px-6 py-6 text-sm">
        {rows.map(([label, value]) => (
          <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0" key={label}>
            <dt className="text-slate-500">{label}</dt>
            <dd className="font-mono text-right text-slate-900">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="px-6 pb-6 text-xs text-slate-500">{values.note}</p>
    </aside>
  </>
}

function FixtureDrawer({ fixture, onClose }: { fixture: any; onClose: () => void }) {
  const values = fixtureDrawerValues(fixture)

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [onClose])

  return <>
    <button
      type="button"
      className="fixed inset-0 z-40 cursor-default bg-slate-950/30"
      aria-label="关闭夹具明细"
      onClick={onClose}
    />
    <aside
      id="fixture-cost-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fixture-cost-drawer-title"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto bg-white shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
        <h2 id="fixture-cost-drawer-title" className="text-lg font-semibold">夹具1</h2>
        <button
          type="button"
          className="flex size-10 items-center justify-center rounded text-2xl text-slate-500 hover:bg-slate-100"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      <dl className="space-y-5 px-6 py-6 text-sm">
        <div>
          <dt className="text-slate-500">数量：</dt>
          <dd className="mt-1 text-slate-900">{values.count}</dd>
        </div>
        <div>
          <dt className="text-slate-500">夹具材料：</dt>
          <dd className="mt-1 text-slate-900">{values.material}</dd>
        </div>
        <div>
          <dt className="text-slate-500">夹具体积：</dt>
          <dd className="mt-1 text-slate-900">{values.volume}</dd>
        </div>
        <div>
          <dt className="text-slate-500">夹具材料费用：</dt>
          <dd className="mt-1 text-slate-900">{values.materialCost}</dd>
        </div>
        <div>
          <dt className="text-slate-500">夹具加工费用：</dt>
          <dd className="mt-1 text-slate-900">{values.processingCost}</dd>
        </div>
      </dl>
    </aside>
  </>
}

export function CostBreakdown({
  quote,
  uiCost,
  quoteSummary,
}: {
  quote: any
  uiCost: any
  quoteSummary: any
}) {
  const [openDrawer, setOpenDrawer] = useState<
    "material" | "machining" | "fixture" | "programming" | "inspect" | "scrap" | null
  >(null)
  const maxCost = Math.max(1, ...COST_ROWS.map(([key]) => costValue(quote, uiCost, key)))

  return <>
    <Card className="p-5">
      <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">03</div>
      <div className="mb-3 font-medium">为什么是这个报价？（成本构成）</div>
      <div className="space-y-2">
        {COST_ROWS.map(([key, label]) => {
          const value = costValue(quote, uiCost, key)
          const content = <>
            <div className="text-left text-slate-500">
              {label}
              {HANDBOOK_PENDING_KEYS.has(key) && (
                <div className="mt-0.5 text-[10px] leading-4 text-slate-400">{HANDBOOK_PENDING_NOTE}</div>
              )}
            </div>
            <div className="h-2 rounded bg-slate-100">
              <div
                className="h-2 rounded bg-blue-600"
                style={{ width: `${Math.min(100, value / maxCost * 100)}%` }}
              />
            </div>
            <div className="text-right">
              ¥{key === "fixture"
                || key === "material"
                || key === "machining"
                || key === "inspect"
                || key === "toolwear"
                || key === "scrap"
                ? value.toFixed(2)
                : yen(value)}
            </div>
          </>

          return key === "fixture"
            || key === "material"
            || key === "machining"
            || key === "programming"
            || key === "inspect"
            || key === "scrap" ? (
            <button
              key={key}
              type="button"
              className="grid min-h-11 w-full grid-cols-[72px_1fr_64px] items-center gap-2 rounded text-sm hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 md:min-h-0 md:grid-cols-[96px_1fr_72px]"
              aria-expanded={openDrawer === key}
              aria-controls={`${key}-cost-drawer`}
              onClick={() => setOpenDrawer(key)}
            >
              {content}
            </button>
          ) : (
            <div
              key={key}
              className="grid grid-cols-[72px_1fr_64px] items-center gap-2 text-sm md:grid-cols-[96px_1fr_72px]"
            >
              {content}
            </div>
          )
        })}
      </div>
      <div className="mt-3 text-sm text-slate-600">
        预估单件利润 ¥{yen(number(quoteSummary?.amount) - number(quoteSummary?.cost))}
        {" · "}
        最终报价 ¥{yen(quoteSummary?.amount)}
      </div>
    </Card>
    {openDrawer === "material" && (
      <MaterialDrawer
        material={quote?.material_cost_breakdown}
        onClose={() => setOpenDrawer(null)}
      />
    )}
    {openDrawer === "machining" && (
      <MachiningDrawer
        labor={quote?.labor_cost_breakdown}
        sequence={quote?.process_sequence || []}
        onClose={() => setOpenDrawer(null)}
      />
    )}
    {openDrawer === "fixture" && (
      <FixtureDrawer fixture={quote?.fixture} onClose={() => setOpenDrawer(null)} />
    )}
    {openDrawer === "programming" && (
      <ProgrammingDrawer quote={quote} onClose={() => setOpenDrawer(null)} />
    )}
    {openDrawer === "inspect" && (
      <InspectDrawer
        inspectFee={uiCost?.inspect}
        onClose={() => setOpenDrawer(null)}
      />
    )}
    {openDrawer === "scrap" && (
      <ScrapDrawer
        scrap={quote?.scrap_cost_breakdown}
        onClose={() => setOpenDrawer(null)}
      />
    )}
  </>
}
