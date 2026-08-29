import { useEffect, useState } from "react"
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
  const [fixtureOpen, setFixtureOpen] = useState(false)
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
              ¥{key === "fixture" ? value.toFixed(2) : yen(value)}
            </div>
          </>

          return key === "fixture" ? (
            <button
              key={key}
              type="button"
              className="grid min-h-11 w-full grid-cols-[72px_1fr_64px] items-center gap-2 rounded text-sm hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 md:min-h-0 md:grid-cols-[96px_1fr_72px]"
              aria-expanded={fixtureOpen}
              aria-controls="fixture-cost-drawer"
              onClick={() => setFixtureOpen(true)}
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
    {fixtureOpen && (
      <FixtureDrawer fixture={quote?.fixture} onClose={() => setFixtureOpen(false)} />
    )}
  </>
}
