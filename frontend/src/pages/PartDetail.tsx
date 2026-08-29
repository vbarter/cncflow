import { useEffect, useState } from "react"
import { Button, Card, Input, Select } from "../components/ui"
import { CostBreakdown } from "../components/CostBreakdown"
import { FeatureReview } from "../components/FeatureReview"
import { ProcessSequenceEditor } from "../components/ProcessSequenceEditor"
import { json } from "../api"
import { hoursLabel, quoteHours } from "../quoteHours"
import {
  confidenceColumns,
  DIMENSION_LABEL,
  EMPTY_DEDUCTION_TEXT,
  formatDeduction,
  liveConfidenceValue,
} from "../quoteConfidence"
import { quoteSuggestedDays, suggestedDaysLabel } from "../suggestedDays"

function yen(n: any) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(0) : "—"
}

function featId(f: any, i: number) {
  return String(f.feature_id || f.id || `f${i}`)
}

export function PartDetail({ id, go }: { id: string; go: (h: string) => void }) {
  const [part, setPart] = useState<any>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<"engineer" | "boss">("engineer")
  const [fieldEpoch, setFieldEpoch] = useState(0)
  async function load() { setPart(await json<any>("/parts/" + id)) }
  useEffect(() => { load().catch(e => setErr(e.message)) }, [id])
  async function patch(body: object) {
    try {
      setBusy(true); setErr("")
      setPart(await json<any>("/parts/" + id, { method: "PATCH", body: JSON.stringify(body) }))
    } catch (e: any) {
      setErr(e.message)
      setFieldEpoch(value => value + 1)
    } finally { setBusy(false) }
  }
  async function patchProcess(body: object) {
    try {
      setBusy(true); setErr("")
      setPart(await json<any>("/parts/" + id + "/process-sequence", { method: "PATCH", body: JSON.stringify(body) }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  async function act(path: string) {
    try {
      setBusy(true); setErr("")
      setPart(await json<any>(path, { method: "POST", body: "{}" }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  if (!part) return <div className="text-sm text-slate-500">{err || "加载中…"}</div>
  const q = part.quote || {}
  const quote = q.quote || {}
  const ui = q.ui_cost || {}
  const risk = q.risk || {}
  const deductions = Array.isArray(q.deductions)
    ? q.deductions
    : (Array.isArray(risk.deductions) ? risk.deductions : [])
  const riskCount = deductions.length || risk.tags?.length || 0
  const locked = part.status === "confirmed"
  const recommend = risk.customer_forbidden ? "建议暂缓" : (risk.level === "high" ? "建议暂缓" : "建议接单")
  const reviewFeats = (q.review_features || q.features || part.parsed_features || []).map((f: any, i: number) => ({
    ...f, feature_id: featId(f, i),
  }))
  const confidenceBreakdown = confidenceColumns(deductions)
  const overallConfidence = liveConfidenceValue(q.confidence)
  const meshAvailable = Boolean(part.mesh?.available)

  function toggleFeat(fid: string, checked: boolean) {
    const ids = reviewFeats
      .filter((f: any) => {
        const on = f.selected === false ? false : true
        return f.feature_id === fid ? checked : on
      })
      .map((f: any) => f.feature_id)
    patch({ selected_feature_ids: ids })
  }

  const costCard = (
    <CostBreakdown quote={q} uiCost={ui} quoteSummary={quote} />
  )

  const actions = (
    <div className="flex flex-col gap-3 md:flex-row">
      <Button className="min-h-11 md:min-h-10" disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认报价</Button>
      <Button className="min-h-11 md:min-h-10" variant="outline" disabled={locked || busy} onClick={() => act("/parts/" + id + "/abandon")}>废弃</Button>
      <Button className="min-h-11 md:min-h-10" variant="ghost" onClick={() => go("inquiry/" + part.inquiry_id)}>回询价单</Button>
    </div>
  )

  const decision = (withConfirm: boolean) => (
    <section className="flex flex-col gap-4 rounded bg-slate-900 px-4 py-5 text-white md:flex-row md:flex-nowrap md:items-center md:justify-between md:px-6">
      <div className="min-w-0 flex-1">
        <div className="text-xs uppercase tracking-wide text-slate-400">01 AI QUOTE DECISION</div>
        <div className="mt-1 text-sm text-emerald-300">{recommend}</div>
        <div className="mt-3 overflow-x-auto">
          <dl className="grid min-w-[720px] grid-cols-6 gap-x-5">
            <div className="min-w-0">
              <dt className="text-xs text-slate-400">单件报价</dt>
              <dd className="mt-1 whitespace-nowrap text-2xl font-semibold">¥{yen(quote.amount)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-slate-400">单件成本</dt>
              <dd className="mt-1 whitespace-nowrap text-base font-medium">¥{yen(quote.cost)}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-slate-400">毛利率</dt>
              <dd className="mt-1 whitespace-nowrap text-base font-medium">{quote.margin ?? "—"}%</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-slate-400">加工时间</dt>
              <dd className="mt-1 whitespace-nowrap text-base font-medium">{hoursLabel(quoteHours(q))}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-slate-400">建议交期</dt>
              <dd className="mt-1 whitespace-nowrap text-base font-medium">{suggestedDaysLabel(quoteSuggestedDays(q))}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-slate-400">工艺风险 · 置信度</dt>
              <dd className="mt-1 whitespace-nowrap text-base font-medium">
                <span className={riskCount ? "text-red-300" : ""}>{riskCount}项</span> · {q.confidence ?? "—"}
              </dd>
            </div>
          </dl>
        </div>
      </div>
      {withConfirm && <Button className="min-h-11 shrink-0 md:min-h-10" disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认本零件报价</Button>}
    </section>
  )

  return <div className="space-y-6">
    <button type="button" className="min-h-11 text-sm text-blue-600 md:min-h-0" onClick={() => go("inquiry/" + part.inquiry_id)}>← 询价单详情</button>
    <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center md:justify-between">
      <div className="text-xs text-slate-500">{part.name} · {part.material_code || "—"} · {part.qty || 1}件</div>
      <div className="flex rounded border border-[#e2e8f0] p-0.5">
        <button type="button" className={`min-h-11 rounded px-3 py-1.5 text-sm md:min-h-0 ${view === "engineer" ? "bg-slate-900 text-white" : "text-slate-600"}`} onClick={() => setView("engineer")}>工程师视图</button>
        <button type="button" className={`min-h-11 rounded px-3 py-1.5 text-sm md:min-h-0 ${view === "boss" ? "bg-slate-900 text-white" : "text-slate-600"}`} onClick={() => setView("boss")}>老板视图</button>
      </div>
    </div>

    {view === "boss" ? <>
      {decision(false)}
      {costCard}
      {actions}
    </> : <>
      {decision(true)}

      <Card className="p-5">
        <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">PDF / PART FIELDS</div>
        <div className="mb-3 flex flex-wrap items-center gap-2 font-medium">
          <span>图纸字段（可手工修改）</span>
          {part.pdf_backfill_status === "applied" && (
            <span className="rounded bg-emerald-50 px-2 py-1 text-xs font-normal text-emerald-700">PDF 已回填</span>
          )}
        </div>
        {part.pdf_backfill_status === "failed" && (
          <div className="mb-4 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" role="status">
            PDF 回填失败：{part.pdf_backfill_warning || "未识别到字段"}；STEP 报价未受影响。
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">材料</div>
            <Input
              key={`${fieldEpoch}-${part.material_code || ""}`}
              disabled={locked || busy}
              defaultValue={part.material_code || ""}
              onBlur={e => {
                const value = e.currentTarget.value.trim()
                if (value !== (part.material_code || "")) patch({ material_code: value })
              }}
            />
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">IT</div>
            <Input
              key={`${fieldEpoch}-${part.tolerance_it ?? ""}`}
              disabled={locked || busy}
              type="number"
              min={1}
              max={18}
              defaultValue={part.tolerance_it ?? ""}
              onBlur={e => {
                const value = e.currentTarget.value
                if (value !== String(part.tolerance_it ?? "")) patch({ tolerance_it: value === "" ? null : Number(value) })
              }}
            />
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">Ra</div>
            <Input
              key={`${fieldEpoch}-${part.roughness_ra ?? ""}`}
              disabled={locked || busy}
              type="number"
              min="0"
              step="any"
              defaultValue={part.roughness_ra ?? ""}
              onBlur={e => {
                const value = e.currentTarget.value
                if (value !== String(part.roughness_ra ?? "")) patch({ roughness_ra: value === "" ? null : Number(value) })
              }}
            />
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">表面处理</div>
            <Input
              key={`${fieldEpoch}-${part.surface_finish || ""}`}
              disabled={locked || busy}
              defaultValue={part.surface_finish || ""}
              onBlur={e => {
                const value = e.currentTarget.value.trim()
                if (value !== (part.surface_finish || "")) patch({ surface_finish: value })
              }}
            />
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">螺纹规格列表</div>
            <Input
              key={`${fieldEpoch}-${(part.thread_specs || []).join(",")}`}
              disabled={locked || busy}
              defaultValue={(part.thread_specs || []).join("、")}
              placeholder="M6、M8×1.25"
              onBlur={e => {
                const specs = e.currentTarget.value.split(/[,，、;；\n]+/).map(value => value.trim()).filter(Boolean)
                if (JSON.stringify(specs) !== JSON.stringify(part.thread_specs || [])) patch({ thread_specs: specs })
              }}
            />
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">数量</div>
            <Input
              key={`${fieldEpoch}-${part.qty || 1}`}
              disabled={locked || busy}
              type="number"
              min={1}
              defaultValue={part.qty || 1}
              onBlur={e => {
                const value = Number(e.currentTarget.value)
                if (Number.isInteger(value) && value > 0 && value !== Number(part.qty || 1)) patch({ qty: value })
              }}
            />
          </label>
        </div>
      </Card>

      <Card className="p-5">
        <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">02</div>
        <div className="mb-3 font-medium">报价可信度</div>
        <div className="flex items-end gap-3">
          <div className="text-3xl font-semibold text-blue-600">{overallConfidence ?? "—"}</div>
          <div className="text-xs text-slate-500">{risk.customer_forbidden ? "置信度偏低，不建议直接给客户" : "可内部确认后出给客户"}</div>
        </div>
        <div className="mt-4 grid items-start gap-3 md:grid-cols-2 xl:grid-cols-4">
          {confidenceBreakdown.map((column) => (
            <div className="min-w-0 rounded border border-[#e2e8f0]" key={column.key}>
              <div className="p-3">
                <div className="text-xs text-slate-500">{column.label}</div>
                <div className="mt-1 text-lg font-medium">{column.score}</div>
                <div className="mt-1 h-1.5 rounded bg-slate-100">
                  <div className="h-1.5 rounded bg-blue-600" style={{ width: `${column.score}%` }} />
                </div>
              </div>
              <details className="border-t border-slate-200" open>
                <summary className="cursor-pointer bg-[#f8fafc] px-3 py-2 text-xs text-slate-500">
                  扣分项（{column.deductions.length}）
                </summary>
                {column.deductions.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[280px] text-left text-xs">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="px-3 py-2 font-medium">原因</th>
                          <th className="w-14 px-2 py-2 text-right font-medium">扣分</th>
                          <th className="w-24 px-2 py-2 font-medium">归类</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 text-slate-600">
                        {column.deductions.map((item, i) => (
                          <tr key={`${item.ruleId}-${i}`}>
                            <td className="px-3 py-2">{item.reason}</td>
                            <td className="px-2 py-2 text-right font-medium text-slate-700">
                              {formatDeduction(item.deduction)}
                            </td>
                            <td className="px-2 py-2">
                              {item.dimension
                                ? `${item.dimension} ${DIMENSION_LABEL[item.dimension] || "—"}`
                                : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="px-3 py-3 text-xs text-slate-400">{EMPTY_DEDUCTION_TEXT}</div>
                )}
              </details>
            </div>
          ))}
        </div>
      </Card>

      {costCard}

      <Card className="p-5">
        <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">04</div>
        <div className="mb-3 font-medium">Feature 模型审查</div>
        <FeatureReview
          partId={id}
          features={reviewFeats}
          processSequence={q.process_sequence || []}
          meshAvailable={meshAvailable}
          locked={locked}
          busy={busy}
          onToggle={toggleFeat}
          onPatchFeature={patch}
          onPatchProcess={patchProcess}
        />
        {!!(risk.tags || []).length && <div className="mt-3 text-xs text-amber-700">风险：{(risk.tags || []).join("、")}</div>}
      </Card>

      <Card className="p-5">
        <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">05</div>
        <div className="mb-3 font-medium">加工工艺方案</div>
        <div className="mb-4 grid gap-4 md:grid-cols-4">
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">滑轴（加工策略）</div>
            <Select disabled={locked || busy} value={q.slider?.slider || part.slider || "标准"} onChange={e => patch({ slider: e.target.value })}>
              <option>保守</option><option>偏保守</option><option>标准</option><option>偏激进</option><option>激进</option>
            </Select>
          </label>
        </div>
        {q.equipment && <div className="mb-2 text-xs text-slate-500">设备 {q.equipment.model || "—"} · {q.equipment.type || "—"} · {q.equipment.hourly_rate != null ? `${q.equipment.hourly_rate} 元/h` : "—"}</div>}
        <ProcessSequenceEditor
          sequence={q.process_sequence || []}
          hasOverrides={Boolean((q.process_overrides || []).length)}
          locked={locked}
          busy={busy}
          onPatch={patchProcess}
        />
        {q.validation && <div className="mt-3 text-xs text-slate-600">
          防错 {q.validation.ok ? "通过" : `${(q.validation.items || []).length}项`}
          {(q.validation.items || []).length ? `：${(q.validation.items || []).map((v: any) => `STEP ${String(v.order || "").padStart(2, "0")} ${v.status}`).join("、")}` : ""}
        </div>}
      </Card>

      {actions}
    </>}
    {err && <div className="text-sm text-red-700">{err}</div>}
  </div>
}
