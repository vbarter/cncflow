import { useEffect, useState } from "react"
import { Badge, Button, Card, Select } from "../components/ui"
import { json } from "../api"

const COST_LABEL: Record<string, string> = {
  material: "材料", machining: "加工", setup: "装夹", programming: "编程",
  inspect: "检测", toolwear: "刀具损耗", scrap: "报废",
}

function yen(n: any) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(0) : "—"
}

export function PartDetail({ id, go }: { id: string; go: (h: string) => void }) {
  const [part, setPart] = useState<any>(null)
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
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
  return <div className="space-y-6">
    <button type="button" className="text-sm text-blue-600" onClick={() => go("inquiry/" + part.inquiry_id)}>← 询价单详情</button>
    <div className="text-xs text-slate-500">{part.name} · {part.material_code || "—"} · {part.qty || 1}件</div>

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
      <Button disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认本次零件报价</Button>
    </div>

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

    <Card className="p-5">
      <div className="mb-3 font-medium">特征审查</div>
      <div className="space-y-2 text-sm">{(q.features || []).length ? (q.features || []).map((f: any, i: number) => (
        <div key={f.feature_id || i} className="flex justify-between border-b border-[#e2e8f0] py-2">
          <span>{f.feature_id || f.type} · {f.type}</span>
          <span className="text-slate-500">{f.plan?.difficulty?.level || f.plan?.machinability?.level || ""}</span>
        </div>
      )) : <div className="text-slate-400">暂无特征</div>}</div>
      {!!(risk.tags || []).length && <div className="mt-3 text-xs text-amber-700">风险：{(risk.tags || []).join("、")}</div>}
    </Card>

    <Card className="p-5">
      <div className="mb-3 font-medium">加工工艺方案</div>
      <div className="space-y-2 text-sm">{(q.process_sequence || []).length ? (q.process_sequence || []).map((s: any, i: number) => (
        <div key={i} className="flex justify-between border-b border-[#e2e8f0] py-2">
          <span>STEP {String(s.order || i + 1).padStart(2, "0")} · {s.name || s.op || s.process || s.feature_id || "工序"}</span>
          <span className="text-slate-500">{s.minutes ? `${Number(s.minutes).toFixed(1)} min` : ""}</span>
        </div>
      )) : <div className="text-slate-400">暂无工序。改滑轴会触发重算。</div>}</div>
    </Card>

    <div className="flex gap-3">
      <Button disabled={locked || part.status !== "quoted" || busy} onClick={() => act("/parts/" + id + "/confirm")}>确认报价</Button>
      <Button variant="outline" disabled={locked || busy} onClick={() => act("/parts/" + id + "/abandon")}>废弃</Button>
      <Button variant="ghost" onClick={() => go("inquiry/" + part.inquiry_id)}>回询价单</Button>
    </div>
    {err && <div className="text-sm text-red-700">{err}</div>}
  </div>
}
