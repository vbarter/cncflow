import { useEffect, useState } from "react"
import { Badge, Button, Card } from "../components/ui"
import { json } from "../api"

const UI: Record<string, string> = {
  quoted: "待审核", confirmed: "已完成", parsing: "报价中", quoting: "报价中",
  revising: "报价中", draft: "待处理", need_params: "待处理", parse_failed: "解析失败", abandoned: "已废弃",
}

function yen(n: any) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return Number.isFinite(v) ? v.toFixed(0) : "—"
}

export function InquiryDetail({ id, go }: { id: string; go: (h: string) => void }) {
  const [inq, setInq] = useState<any>(null)
  const [err, setErr] = useState("")
  useEffect(() => { json<any>("/inquiries/" + id).then(setInq).catch(e => setErr(e.message)) }, [id])
  if (!inq) return <div className="text-sm text-slate-500">{err || "加载中…"}</div>
  const parts = inq.parts || []
  const total = parts.reduce((s: number, p: any) => s + (Number(p.quote?.quote?.amount) || 0) * (Number(p.qty) || 1), 0)
  function exportQuote() {
    const blob = new Blob([JSON.stringify({
      rfq: inq.title, customer: inq.customer, project: inq.project, due_date: inq.due_date,
      parts: parts.map((p: any) => ({
        name: p.name, qty: p.qty, material: p.material_code, status: p.status,
        amount: p.quote?.quote?.amount, cost: p.quote?.quote?.cost, margin: p.quote?.quote?.margin,
      })),
      total,
    }, null, 2)], { type: "application/json" })
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob)
    a.download = `${inq.title || "RFQ"}-报价单.json`
    a.click()
  }
  return <div className="space-y-6">
    <button type="button" className="text-sm text-blue-600" onClick={() => go("")}>← 返回报价工作台</button>
    <div className="flex items-center justify-between rounded bg-slate-900 px-6 py-5 text-white">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-400">{inq.title || "RFQ"} / {inq.customer || "未填客户"}</div>
        <div className="mt-1 font-serif text-2xl font-semibold">{parts.length} 个零件综合报价</div>
        <div className="mt-1 text-sm text-slate-300">合计 ¥{yen(total)} · 交期 {inq.due_date || "—"}</div>
      </div>
      <Button onClick={exportQuote}>导出报价单</Button>
    </div>
    <div>
      <div className="mb-3 text-sm font-medium text-slate-800">零件报价列表</div>
      <div className="space-y-3">{parts.map((p: any) => {
        const q = p.quote?.quote
        const risk = p.quote?.risk
        return <Card key={p.id} className="flex cursor-pointer items-center gap-4 p-4 hover:border-blue-300" onClick={() => go("part/" + p.id)}>
          <div className="grid h-16 w-16 shrink-0 place-items-center rounded bg-slate-100 text-[10px] text-slate-400">3D 视图</div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="font-medium text-slate-900">{p.name}</div>
              <Badge>{UI[p.status] || p.status}</Badge>
              {risk?.level && risk.level !== "low" && <span className="text-xs text-amber-600">存在工艺风险</span>}
            </div>
            <div className="mt-1 text-xs text-slate-500">{p.qty || 1}件 · {p.material_code || "—"}</div>
            <div className="mt-2 grid grid-cols-3 gap-3 text-sm text-slate-700">
              <div>单件报价 <span className="font-semibold">¥{yen(q?.amount)}</span></div>
              <div>单件成本 ¥{yen(q?.cost)}</div>
              <div>毛利 {q?.margin ?? "—"}%</div>
            </div>
          </div>
          <span className="text-sm text-blue-600">查看详情 →</span>
        </Card>
      })}</div>
    </div>
    {err && <div className="text-sm text-red-700">{err}</div>}
  </div>
}
