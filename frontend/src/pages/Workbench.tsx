import { useEffect, useState } from "react"
import { Plus } from "lucide-react"
import { Badge, Button, Card, Input, Select } from "../components/ui"
import { json } from "../api"
import { hoursLabel, quoteHours } from "../quoteHours"
import { inquirySuggestedDays, suggestedDaysLabel } from "../suggestedDays"

const LABELS: Record<string, string> = { pending: "待处理", quoting: "报价中", review: "待审核", done: "已完成" }

function yen(n: any) {
  const v = Number(n)
  return Number.isFinite(v) && v ? `¥${v.toFixed(0)}` : "—"
}

function totals(inq: any) {
  const parts = inq.parts || []
  let amount = 0, cost = 0, hours = 0
  let hasHours = false
  for (const p of parts) {
    const q = p.quote?.quote || {}
    const qty = Number(p.qty) || 1
    amount += (Number(q.amount) || 0) * qty
    cost += (Number(q.cost) || 0) * qty
    const h = quoteHours(p.quote)
    if (h != null) { hours += h * qty; hasHours = true }
  }
  const margin = amount ? ((amount - cost) / amount) * 100 : 0
  return {
    amount,
    cost,
    margin,
    hours: hasHours ? Math.round(hours * 10) / 10 : null,
    suggestedDays: inquirySuggestedDays(parts),
    n: parts.length,
  }
}

export function Workbench({ go }: { go: (h: string) => void }) {
  const [items, setItems] = useState<any[]>([])
  const [filter, setFilter] = useState("")
  const [q, setQ] = useState("")
  useEffect(() => {
    json<{ items: any[] }>("/inquiries" + (filter ? `?ui_status=${filter}` : "")).then(d => setItems(d.items)).catch(() => setItems([]))
  }, [filter])
  const counts = items.reduce((a: any, i) => { a[i.ui_status] = (a[i.ui_status] || 0) + 1; return a }, { pending: 0, quoting: 0, review: 0, done: 0 })
  const monthAmount = items.reduce((s, i) => s + totals(i).amount, 0)
  const shown = items.filter(i => {
    if (!q.trim()) return true
    const blob = `${i.title || ""} ${i.customer || ""} ${i.project || ""}`
    return blob.toLowerCase().includes(q.trim().toLowerCase())
  })
  return <div className="space-y-6">
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-500">QUOTE OPERATIONS</div>
        <h1 className="font-serif mt-2 text-3xl font-semibold tracking-tight text-slate-900">报价工作台</h1>
        <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">持续推进每一笔询价，并在关键节点完成工艺审核。</p>
      </div>
      <Button className="min-h-11 md:min-h-10" onClick={() => go("new")}><Plus className="mr-2" size={16} />新建报价</Button>
    </div>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {(["pending", "quoting", "review", "done"] as const).map(k => (
        <Card key={k} className={`min-h-11 cursor-pointer p-4 ${filter === k ? "border-blue-600" : ""}`} onClick={() => setFilter(filter === k ? "" : k)}>
          <div className="text-xs text-slate-500">{LABELS[k]}</div>
          <div className="mt-2 text-2xl font-semibold">{counts[k] || 0}</div>
        </Card>
      ))}
      <Card className="col-span-2 p-4 md:col-span-1">
        <div className="text-xs text-slate-500">本月报价金额</div>
        <div className="mt-2 text-2xl font-semibold">{yen(monthAmount)}</div>
      </Card>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Input className="max-w-xs" placeholder="搜索询价单、客户或零件" value={q} onChange={e => setQ(e.target.value)} />
      <Select value={filter} onChange={e => setFilter(e.target.value)} className="w-36">
        <option value="">全部状态</option>
        <option value="pending">待处理</option>
        <option value="quoting">报价中</option>
        <option value="review">待审核</option>
        <option value="done">已完成</option>
      </Select>
      <div className="text-xs text-slate-400">{shown.length} 条询价单</div>
    </div>
    <div className="space-y-3 md:hidden">
      {shown.map(i => {
        const t = totals(i)
        return <Card key={i.id} className="min-h-11 cursor-pointer p-4" onClick={() => go("inquiry/" + i.id)}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-mono text-xs text-slate-500">单号</div>
              <div className="truncate font-medium text-slate-900">{i.title || "—"}</div>
            </div>
            <Badge>{LABELS[i.ui_status] || i.ui_status}</Badge>
          </div>
          <div className="mt-3 flex items-end justify-between gap-3">
            <div>
              <div className="text-xs text-slate-500">客户</div>
              <div className="text-sm font-medium">{i.customer || "—"}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-slate-500">金额</div>
              <div className="text-sm font-semibold">{yen(t.amount)}</div>
            </div>
          </div>
          <div className="mt-3 text-xs text-slate-500">交期要求 {i.due_date || "—"} · 建议交期 {suggestedDaysLabel(t.suggestedDays)}</div>
        </Card>
      })}
      {!shown.length && <Card className="px-4 py-10 text-center text-sm text-slate-500">还没有询价单</Card>}
    </div>
    <Card className="hidden overflow-x-auto md:block">
      <table className="w-full text-left text-sm">
        <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
          <th className="px-4 py-3">询价单号</th><th>客户</th><th>零件</th><th>报价金额</th><th>成本</th><th>综合毛利</th><th>加工时间</th><th>交期</th><th>状态</th><th>操作</th>
        </tr></thead>
        <tbody>
          {shown.map(i => {
            const t = totals(i)
            return <tr key={i.id} className="border-b border-slate-100 hover:bg-slate-50">
              <td className="px-4 py-3 font-mono text-xs">{i.title || "—"}</td>
              <td className="font-medium">{i.customer || "—"}</td>
              <td>{t.n} 个零件</td>
              <td>{yen(t.amount)}</td>
              <td>{yen(t.cost)}</td>
              <td>{t.amount ? `${t.margin.toFixed(0)}%` : "—"}</td>
              <td>{hoursLabel(t.hours)}</td>
              <td><div>{i.due_date || "—"}</div><div className="text-xs text-slate-500">建议 {suggestedDaysLabel(t.suggestedDays)}</div></td>
              <td><Badge>{LABELS[i.ui_status] || i.ui_status}</Badge></td>
              <td><button type="button" className="text-sm text-blue-600" onClick={() => go("inquiry/" + i.id)}>查看询价单 →</button></td>
            </tr>
          })}
          {!shown.length && <tr><td colSpan={10} className="px-4 py-10 text-center text-slate-500">还没有询价单</td></tr>}
        </tbody>
      </table>
    </Card>
  </div>
}
