import React, { type ReactNode } from "react"

export function PartQuoteDecision({
  recommend,
  quote,
  cost,
  margin,
  machiningTime,
  suggestedDelivery,
  riskCount,
  confidence,
  confirmAction,
}: {
  recommend: string
  quote: ReactNode
  cost: ReactNode
  margin: ReactNode
  machiningTime: ReactNode
  suggestedDelivery: ReactNode
  riskCount: number
  confidence: ReactNode
  confirmAction?: ReactNode
}) {
  return (
    <section className="flex flex-col gap-4 rounded bg-slate-900 px-4 py-5 text-white md:px-6 lg:flex-row lg:flex-nowrap lg:items-center lg:justify-between">
      <div className="min-w-0 flex-1">
        <div className="text-xs uppercase tracking-wide text-slate-400">01 AI QUOTE DECISION</div>
        <div className="mt-1 text-sm text-emerald-300">{recommend}</div>
        <dl className="mt-3 grid w-full grid-cols-3 gap-x-5 gap-y-3 lg:grid-cols-6">
          <div className="min-w-0">
            <dt className="text-xs text-slate-400">单件报价</dt>
            <dd className="mt-1 whitespace-nowrap text-2xl font-semibold">{quote}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-slate-400">单件成本</dt>
            <dd className="mt-1 whitespace-nowrap text-base font-medium">{cost}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-slate-400">毛利率</dt>
            <dd className="mt-1 whitespace-nowrap text-base font-medium">{margin}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-slate-400">加工时间</dt>
            <dd className="mt-1 whitespace-nowrap text-base font-medium">{machiningTime}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-slate-400">建议交期</dt>
            <dd className="mt-1 whitespace-nowrap text-base font-medium">{suggestedDelivery}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-xs text-slate-400">工艺风险 · 置信度</dt>
            <dd className="mt-1 whitespace-nowrap text-base font-medium">
              <span className={riskCount ? "text-red-300" : ""}>{riskCount}项</span> · {confidence}
            </dd>
          </div>
        </dl>
      </div>
      {confirmAction}
    </section>
  )
}
