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

function MachiningDrawer({ labor, onClose }: { labor: any; onClose: () => void }) {
  const groups = Array.isArray(labor?.groups) ? labor.groups : []
  const changeover = labor?.changeover || {}

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
                  {[
                    ["工序名称", operation.name || "—"],
                    ["设备名称", operation.equipment_name || "—"],
                    ["刀具 SKU", operation.tool_sku || "—"],
                    ["加工时长 (min)", number(operation.minutes).toFixed(2)],
                    ["设备费率 (¥/h)", number(operation.hourly_rate).toFixed(0)],
                    ["工序费用", `¥${number(operation.cost).toFixed(2)}`],
                  ].map(([label, value]) => (
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
          <h3 id="machining-changeover" className="mb-3 font-medium text-slate-900">换夹</h3>
          <dl className="divide-y divide-slate-100 rounded border border-slate-200">
            {[
              ["夹具换夹时长", `${number(changeover.minutes).toFixed(2)} min`],
              ["加工设备", changeover.equipment_name || "—"],
              ["设备费率", `¥${number(changeover.hourly_rate).toFixed(0)}/h`],
              ["夹具换夹费用", `¥${number(changeover.cost).toFixed(2)}`],
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
  const [openDrawer, setOpenDrawer] = useState<"material" | "machining" | "fixture" | null>(null)
  const maxCost = Math.max(1, ...COST_ROWS.map(([key]) => costValue(quote, uiCost, key)))

  return <>
    <Card className="p-5">
      <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">03</div>
      <div className="mb-3 font-medium">为什么是这个报价？（成本构成）</div>
      <div className="space-y-2">
        {COST_ROWS.map(([key, label]) => {
          const value = costValue(quote, uiCost, key)
          const content = <>
            <div className="text-left text-slate-500">{label}</div>
            <div className="h-2 rounded bg-slate-100">
              <div
                className="h-2 rounded bg-blue-600"
                style={{ width: `${Math.min(100, value / maxCost * 100)}%` }}
              />
            </div>
            <div className="text-right">
              ¥{key === "fixture" || key === "material" || key === "machining"
                ? value.toFixed(2)
                : yen(value)}
            </div>
          </>

          return key === "fixture" || key === "material" || key === "machining" ? (
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
        onClose={() => setOpenDrawer(null)}
      />
    )}
    {openDrawer === "fixture" && (
      <FixtureDrawer fixture={quote?.fixture} onClose={() => setOpenDrawer(null)} />
    )}
  </>
}
