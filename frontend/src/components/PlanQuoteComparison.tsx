import React from "react"
import { Card } from "./ui"

function money(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? `¥${number.toFixed(2)}` : "—"
}

function hours(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)} h` : "—"
}

export function PlanQuoteComparison({ quote }: { quote: any }) {
  const blank = quote?.blank
  const candidates = Array.isArray(quote?.candidates) ? quote.candidates : []
  const comparison = Array.isArray(quote?.comparison) ? quote.comparison : []
  if (!blank || comparison.length < 2) return null
  const candidateById = new Map(candidates.map((candidate: any) => [candidate.id, candidate]))

  return <Card className="p-5">
    <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">PHASE 1 / ROUTE OPTIONS</div>
    <div className="font-medium">毛坯与加工方案比较</div>
    <div className="mt-3 rounded border border-[#e2e8f0] bg-[#f8fafc] px-4 py-3">
      <div className="text-xs text-slate-500">建议毛坯</div>
      <div className="mt-1 text-sm font-medium text-slate-900">
        {blank.label} · {blank.suggested_stock_size?.display || "—"}
      </div>
      <div className="mt-1 text-xs text-slate-500">
        零件包络 {Object.values(blank.envelope_mm || {}).join(" × ")} mm · {blank.rule}
      </div>
    </div>
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
          <tr>
            <th className="px-3 py-2 font-normal">方案</th>
            <th className="px-3 py-2 font-normal">设备</th>
            <th className="px-3 py-2 text-right font-normal">装夹</th>
            <th className="px-3 py-2 text-right font-normal">加工时间</th>
            <th className="px-3 py-2 text-right font-normal">加工成本</th>
            <th className="px-3 py-2 text-right font-normal">总成本</th>
            <th className="px-3 py-2 text-right font-normal">报价</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {comparison.map((row: any) => {
            const candidate: any = candidateById.get(row.plan_id)
            return <tr key={row.plan_id}>
              <td className="px-3 py-3">
                <div className="font-medium text-slate-900">{row.label}</div>
                <div className="mt-1 text-xs text-slate-400">
                  {candidate?.source === "user" ? "用户给定" : candidate?.source === "llm" ? "AI 生成" : "规则生成"}
                </div>
              </td>
              <td className="px-3 py-3 text-slate-600">{row.machine}</td>
              <td className="px-3 py-3 text-right">{row.setup_count}</td>
              <td className="px-3 py-3 text-right">{hours(row.machining_time_hours)}</td>
              <td className="px-3 py-3 text-right">{money(row.machining_cost)}</td>
              <td className="px-3 py-3 text-right font-medium">{money(row.total_cost)}</td>
              <td className="px-3 py-3 text-right font-medium text-blue-700">{money(row.quoted_amount)}</td>
            </tr>
          })}
        </tbody>
      </table>
    </div>
    {!!quote.warnings?.length && (
      <div className="mt-3 text-xs text-amber-700">{quote.warnings.join("；")}</div>
    )}
  </Card>
}
