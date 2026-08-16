import { useEffect, useState } from "react"
import { Button, Card, Select } from "../components/ui"
import { json } from "../api"

const COST_LABEL: Record<string, string> = {
  material: "材料", machining: "加工", setup: "装夹", programming: "编程",
  inspect: "检测", toolwear: "刀具损耗", scrap: "报废",
}

const MATERIALS = ["AL6061-T6", "SUS304", "AL7075", "POM", "铝合金", "钢", "不锈钢"]
const IT_OPTIONS = [11, 8, 7, 6]
const RA_OPTIONS = [3.2, 1.6, 0.8]

function yen(n: any) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(0) : "—"
}

function featDims(f: any) {
  const dim = f.dimensions || {}
  const d = dim.diameter_mm ?? f.diameter_mm
  const depth = dim.depth_mm ?? f.depth_mm
  const bits: string[] = []
  if (d != null) bits.push(`Ø${d}`)
  if (depth != null) bits.push(`深${depth}`)
  const ht = f.hole_type === "through" ? "通孔" : f.hole_type === "blind" ? "盲孔" : f.hole_type
  if (ht) bits.push(ht)
  if (f.position_type) bits.push(f.position_type)
  if (f.cut_depth_mm != null) bits.push(`cut=${f.cut_depth_mm}`)
  if (f.length != null && f.width != null) bits.push(`${f.length}×${f.width}`)
  return bits.join(" ")
}

function featId(f: any, i: number) {
  return String(f.feature_id || f.id || `f${i}`)
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
  const locked = part.status === "confirmed"
  const recommend = risk.customer_forbidden ? "建议暂缓" : (risk.level === "high" ? "存在工艺风险" : "建议接单")
  const maxCost = Math.max(1, ...Object.values(ui).map((v: any) => Number(v) || 0))
  const reviewFeats = q.review_features || q.features || part.parsed_features || []
  const materials = MATERIALS.includes(part.material_code) || !part.material_code
    ? MATERIALS
    : [part.material_code, ...MATERIALS]

  function patchParams(next: { material?: string; tolerance_it?: number; roughness_ra?: number }) {
    patch({
      material: next.material ?? part.material_code,
      tolerance_it: next.tolerance_it ?? part.tolerance_it ?? 11,
      roughness_ra: next.roughness_ra ?? part.roughness_ra ?? 3.2,
    })
  }

  function toggleFeat(fid: string, checked: boolean) {
    const ids = reviewFeats
      .filter((f: any, i: number) => {
        const id = featId(f, i)
        const on = f.selected === false ? false : true
        return id === fid ? checked : on
      })
      .map((f: any, i: number) => featId(f, i))
    patch({ selected_feature_ids: ids })
  }

  const costCard = (
    <Card className="p-5">
      <div className="mb-3 font-medium">为什么是这个报价？（成本构成）</div>
      <div className="space-y-2">{Object.entries(COST_LABEL).map(([k, label]) => {
        const v = Number(ui[k]) || 0
        return <div key={k} className="grid grid-cols-[96px_1fr_72px] items-center gap-2 text-sm">
          <div className="text-slate-500">{label}</div>
          <div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-blue-600" style={{ width: `${Math.min(100, v / maxCost * 100)}%` }} /></div>
          <div className="text-right">¥{yen(v)}</div>
        </div>
      })}</div>
      <div className="mt-3 text-sm text-slate-600">预估单件利润 ¥{yen((quote.amount || 0) - (quote.cost || 0))} · 最终报价 ¥{yen(quote.amount)}</div>
    </Card>
  )

  const actions = (
    <div className="flex gap-3">
      <Button disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认报价</Button>
      <Button variant="outline" disabled={locked || busy} onClick={() => act("/parts/" + id + "/abandon")}>废弃</Button>
      <Button variant="ghost" onClick={() => go("inquiry/" + part.inquiry_id)}>回询价单</Button>
    </div>
  )

  const banner = (withConfirm: boolean) => (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded bg-slate-900 px-6 py-5 text-white">
      <div>
        <div className="text-sm text-emerald-300">{recommend}</div>
        <div className="mt-2 flex flex-wrap gap-6 text-sm">
          <div>单件报价 <span className="text-xl font-semibold">¥{yen(quote.amount)}</span></div>
          <div>单件成本 ¥{yen(quote.cost)}</div>
          <div>毛利率 {quote.margin ?? "—"}%</div>
          <div>工艺风险 <span className={risk.tags?.length ? "text-red-300" : ""}>{risk.tags?.length || 0}项</span></div>
        </div>
      </div>
      {withConfirm && <Button disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认本次零件报价</Button>}
    </div>
  )

  return <div className="space-y-6">
    <button type="button" className="text-sm text-blue-600" onClick={() => go("inquiry/" + part.inquiry_id)}>← 询价单详情</button>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="text-xs text-slate-500">{part.name} · {part.material_code || "—"} · {part.qty || 1}件</div>
      <div className="flex rounded border border-[#e2e8f0] p-0.5">
        <button type="button" className={`rounded px-3 py-1.5 text-sm ${view === "engineer" ? "bg-slate-900 text-white" : "text-slate-600"}`} onClick={() => setView("engineer")}>工程师视图</button>
        <button type="button" className={`rounded px-3 py-1.5 text-sm ${view === "boss" ? "bg-slate-900 text-white" : "text-slate-600"}`} onClick={() => setView("boss")}>老板视图</button>
      </div>
    </div>

    {view === "boss" ? <>
      {banner(false)}
      {costCard}
      {actions}
    </> : <>
      {banner(true)}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5">
          <div className="text-xs text-slate-500">报价可信度</div>
          <div className="mt-2 text-3xl font-semibold text-blue-600">{q.confidence ?? "—"}</div>
          <div className="mt-1 text-xs text-slate-500">{risk.customer_forbidden ? "置信度偏低，不建议直接给客户" : "可内部确认后出给客户"}</div>
        </Card>
        <Card className="p-5">
          <div className="text-xs text-slate-500">滑轴（改参后自动重算）</div>
          <Select disabled={locked || busy} value={q.slider?.slider || part.slider || "标准"} onChange={e => patch({ slider: e.target.value })} className="mt-2">
            <option>保守</option><option>偏保守</option><option>标准</option><option>偏激进</option><option>激进</option>
          </Select>
        </Card>
        <Card className="p-5">
          <div className="text-xs text-slate-500">毛坯尺寸 mm</div>
          <div className="mt-2 text-sm text-slate-800">{[part.length, part.width, part.height].filter(v => v != null).join(" × ") || "待解析"}</div>
          <div className="mt-1 text-xs text-slate-400">状态 {part.status}</div>
        </Card>
      </div>

      <Card className="p-5">
        <div className="mb-3 font-medium">改参</div>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">材料</div>
            <Select disabled={locked || busy} value={part.material_code || "铝合金"} onChange={e => patchParams({ material: e.target.value })}>
              {materials.map(m => <option key={m} value={m}>{m}</option>)}
            </Select>
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">IT</div>
            <Select disabled={locked || busy} value={String(part.tolerance_it || 11)} onChange={e => patchParams({ tolerance_it: Number(e.target.value) })}>
              {IT_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
            </Select>
          </label>
          <label className="block text-sm">
            <div className="mb-1 text-xs text-slate-500">Ra</div>
            <Select disabled={locked || busy} value={String(part.roughness_ra || 3.2)} onChange={e => patchParams({ roughness_ra: Number(e.target.value) })}>
              {RA_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
            </Select>
          </label>
        </div>
        <div className="mt-5 mb-3 font-medium">特征审查</div>
        <div className="space-y-2 text-sm">{reviewFeats.length ? reviewFeats.map((f: any, i: number) => {
          const fid = featId(f, i)
          const checked = f.selected !== false
          const diff = f.plan?.difficulty?.level || f.plan?.machinability?.level || f.difficulty || ""
          return <label key={fid} className="flex items-center justify-between gap-3 border-b border-[#e2e8f0] py-2">
            <span className="flex min-w-0 items-center gap-2">
              <input type="checkbox" disabled={locked || busy} checked={checked} onChange={e => toggleFeat(fid, e.target.checked)} />
              <span>{fid} · {f.type || "特征"}{featDims(f) ? ` · ${featDims(f)}` : ""}</span>
            </span>
            <span className="shrink-0 text-slate-500">{diff}</span>
          </label>
        }) : <div className="text-slate-400">暂无特征</div>}</div>
        {!!(risk.tags || []).length && <div className="mt-3 text-xs text-amber-700">风险：{(risk.tags || []).join("、")}</div>}
      </Card>

      {costCard}

      <Card className="p-5">
        <div className="mb-3 font-medium">加工工艺方案</div>
        <div className="space-y-2 text-sm">{(q.process_sequence || []).length ? (q.process_sequence || []).map((s: any, i: number) => (
          <div key={i} className="flex justify-between border-b border-[#e2e8f0] py-2">
            <span>STEP {String(s.order || i + 1).padStart(2, "0")} · {s.name || s.op || s.process || s.feature_id || "工序"}</span>
            <span className="text-slate-500">{s.minutes ? `${Number(s.minutes).toFixed(1)} min` : ""}</span>
          </div>
        )) : <div className="text-slate-400">暂无工序。改滑轴会触发重算。</div>}</div>
      </Card>

      {actions}
    </>}
    {err && <div className="text-sm text-red-700">{err}</div>}
  </div>
}
