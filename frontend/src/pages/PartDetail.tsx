import { useEffect, useState } from "react"
import { Button, Card, Input, Select } from "../components/ui"
import { FeatureReview } from "../components/FeatureReview"
import { ProcessSequenceEditor } from "../components/ProcessSequenceEditor"
import { json } from "../api"
import { hoursLabel, quoteHours } from "../quoteHours"
import { quoteSuggestedDays, suggestedDaysLabel } from "../suggestedDays"

const COST_LABEL: Record<string, string> = {
  material: "原材料", machining: "加工工时", setup: "装夹", fixture: "夹具",
  programming: "编程", inspect: "检测", toolwear: "刀具损耗", scrap: "不良损耗",
}

function yen(n: any) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(0) : "—"
}

function costValue(q: any, ui: any, key: string) {
  if (ui?.[key] != null && ui[key] !== "") return Number(ui[key]) || 0
  if (key === "fixture") {
    const hit = (q.cost_items || []).find((i: any) => i.code === "FIX")
    return hit ? Number(hit.amount) || 0 : 0
  }
  return 0
}

function featId(f: any, i: number) {
  return String(f.feature_id || f.id || `f${i}`)
}

function confidenceParts(part: any, q: any, reviewFeats: any[]) {
  const holes = reviewFeats.filter((f) => f.subtype === "recognized_hole" || (f.type === "hole" && f.selected !== false))
  const drawing = holes.length ? 88 : (reviewFeats.length ? 52 : 18)
  const process = Number(q.confidence)
  const factory = q.fixture?.is_machinable === false ? 32 : (q.fixture?.type ? 82 : 58)
  const keys = Object.keys(COST_LABEL)
  const ui = q.ui_cost || {}
  const filled = keys.filter((k) => ui[k] != null || (k === "fixture" && (q.cost_items || []).some((i: any) => i.code === "FIX"))).length
  const cost = Math.round((filled / keys.length) * 100)
  const total = Number.isFinite(process) ? process : Math.round((drawing + factory + cost) / 3)
  return [
    { key: "drawing", label: "图纸识别", value: drawing },
    { key: "process", label: "工艺可加工性", value: Number.isFinite(process) ? process : 0 },
    { key: "factory", label: "工厂资源匹配", value: factory },
    { key: "cost", label: "成本数据完整性", value: cost },
    { key: "total", label: "总分", value: total },
  ]
}

export function PartDetail({ id, go }: { id: string; go: (h: string) => void }) {
  const [part, setPart] = useState<any>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<"engineer" | "boss">("engineer")
  async function load() { setPart(await json<any>("/parts/" + id)) }
  useEffect(() => { load().catch(e => setErr(e.message)) }, [id])
  async function patch(body: object) {
    try {
      setBusy(true); setErr("")
      setPart(await json<any>("/parts/" + id, { method: "PATCH", body: JSON.stringify(body) }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
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
  const deductions = q.deductions || risk.deductions || []
  const riskCount = deductions.length || risk.tags?.length || 0
  const locked = part.status === "confirmed"
  const recommend = risk.customer_forbidden ? "建议暂缓" : (risk.level === "high" ? "建议暂缓" : "建议接单")
  const maxCost = Math.max(1, ...Object.keys(COST_LABEL).map((k) => costValue(q, ui, k)))
  const reviewFeats = (q.review_features || q.features || part.parsed_features || []).map((f: any, i: number) => ({
    ...f, feature_id: featId(f, i),
  }))
  const conf = confidenceParts(part, q, reviewFeats)
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
    <Card className="p-5">
      <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">03</div>
      <div className="mb-3 font-medium">为什么是这个报价？（成本构成）</div>
      <div className="space-y-2">{Object.entries(COST_LABEL).map(([k, label]) => {
        const v = costValue(q, ui, k)
        return <div key={k} className="grid grid-cols-[72px_1fr_64px] items-center gap-2 text-sm md:grid-cols-[96px_1fr_72px]">
          <div className="text-slate-500">{label}</div>
          <div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-blue-600" style={{ width: `${Math.min(100, v / maxCost * 100)}%` }} /></div>
          <div className="text-right">¥{yen(v)}</div>
        </div>
      })}</div>
      <div className="mt-3 text-sm text-slate-600">预估单件利润 ¥{yen((quote.amount || 0) - (quote.cost || 0))} · 最终报价 ¥{yen(quote.amount)}</div>
    </Card>
  )

  const actions = (
    <div className="flex flex-col gap-3 md:flex-row">
      <Button className="min-h-11 md:min-h-10" disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认报价</Button>
      <Button className="min-h-11 md:min-h-10" variant="outline" disabled={locked || busy} onClick={() => act("/parts/" + id + "/abandon")}>废弃</Button>
      <Button className="min-h-11 md:min-h-10" variant="ghost" onClick={() => go("inquiry/" + part.inquiry_id)}>回询价单</Button>
    </div>
  )

  const decision = (withConfirm: boolean) => (
    <div className="flex flex-col gap-4 rounded bg-slate-900 px-4 py-5 text-white md:flex-row md:flex-wrap md:items-center md:justify-between md:px-6">
      <div>
        <div className="text-xs uppercase tracking-wide text-slate-400">01 AI QUOTE DECISION</div>
        <div className="mt-1 text-sm text-emerald-300">{recommend}</div>
        <div className="mt-2 flex flex-col gap-2 text-sm md:flex-row md:flex-wrap md:gap-6">
          <div>单件报价 <span className="text-xl font-semibold">¥{yen(quote.amount)}</span></div>
          <div>单件成本 ¥{yen(quote.cost)}</div>
          <div>毛利率 {quote.margin ?? "—"}%</div>
          <div>加工时间 {hoursLabel(quoteHours(q))}</div>
          <div>建议交期 {suggestedDaysLabel(quoteSuggestedDays(q))}</div>
          <div>工艺风险 <span className={riskCount ? "text-red-300" : ""}>{riskCount}项</span> · 置信度 {q.confidence ?? "—"}</div>
        </div>
      </div>
      {withConfirm && <Button className="min-h-11 md:min-h-10" disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认本零件报价</Button>}
    </div>
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
          <div className="text-3xl font-semibold text-blue-600">{conf.find(c => c.key === "total")?.value ?? "—"}</div>
          <div className="text-xs text-slate-500">{risk.customer_forbidden ? "置信度偏低，不建议直接给客户" : "可内部确认后出给客户"}</div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {conf.filter(c => c.key !== "total").map((c) => (
            <div key={c.key}>
              <div className="text-xs text-slate-500">{c.label}</div>
              <div className="mt-1 text-lg font-medium">{c.value}</div>
              <div className="mt-1 h-1.5 rounded bg-slate-100"><div className="h-1.5 rounded bg-blue-600" style={{ width: `${Math.min(100, c.value)}%` }} /></div>
            </div>
          ))}
        </div>
        {deductions.length > 0 && <div className="mt-4 space-y-1 text-xs text-slate-500">
          {deductions.map((item: any, i: number) => (
            <div key={`${item.rule_id}-${i}`}>{item.rule_id} · {item.reason} · -{item.deduction}分</div>
          ))}
        </div>}
      </Card>

      {costCard}

      <Card className="p-5">
        <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">04</div>
        <div className="mb-3 font-medium">Feature 模型审查</div>
        <div className="mb-4 grid gap-4 md:grid-cols-4">
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">滑轴</div>
            <Select disabled={locked || busy} value={q.slider?.slider || part.slider || "标准"} onChange={e => patch({ slider: e.target.value })}>
              <option>保守</option><option>偏保守</option><option>标准</option><option>偏激进</option><option>激进</option>
            </Select>
          </label>
        </div>
        <FeatureReview
          partId={id}
          features={reviewFeats}
          meshAvailable={meshAvailable}
          locked={locked}
          busy={busy}
          onToggle={toggleFeat}
        />
        {!!(risk.tags || []).length && <div className="mt-3 text-xs text-amber-700">风险：{(risk.tags || []).join("、")}</div>}
      </Card>

      <Card className="p-5">
        <div className="mb-1 text-xs uppercase tracking-wide text-slate-400">05</div>
        <div className="mb-3 font-medium">加工工艺方案</div>
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
