import { useEffect, useState } from "react"
import { Plus } from "lucide-react"
import { Badge, Button, Card } from "../components/ui"
import { json } from "../api"

const LABELS: Record<string,string> = { pending:"待处理", quoting:"报价中", review:"待审核", done:"已完成" }

export function Workbench({ go }:{ go:(h:string)=>void }) {
  const [items,setItems]=useState<any[]>([])
  const [filter,setFilter]=useState("")
  useEffect(()=>{ json<{items:any[]}>("/inquiries"+(filter?`?ui_status=${filter}`:"")).then(d=>setItems(d.items)).catch(()=>setItems([])) },[filter])
  const counts = items.reduce((a:any,i)=>{a[i.ui_status]=(a[i.ui_status]||0)+1;return a},{pending:0,quoting:0,review:0,done:0})
  return <div className="space-y-6">
    <div className="flex items-end justify-between"><div><div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-500">QUOTE OPERATIONS</div><h1 className="font-serif mt-2 text-3xl font-semibold tracking-tight text-slate-900">报价工作台</h1><p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">持续推进每一笔询价，并在关键节点完成工艺审核。</p></div><Button onClick={()=>go("new")}><Plus className="mr-2" size={16}/>新建报价</Button></div>
    <div className="grid gap-3 sm:grid-cols-4">{(["pending","quoting","review","done"] as const).map(k=><Card key={k} className="cursor-pointer p-4" onClick={()=>setFilter(filter===k?"":k)}><div className="text-xs text-slate-500">{LABELS[k]}</div><div className="mt-2 text-2xl font-semibold">{counts[k]||0}</div></Card>)}</div>
    <Card className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b border-slate-200 text-xs text-slate-500"><th className="px-4 py-3">客户</th><th>项目</th><th>交期</th><th>状态</th><th>零件</th></tr></thead>
    <tbody>{items.map(i=><tr key={i.id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={()=>go("inquiry/"+i.id)}><td className="px-4 py-3 font-medium">{i.customer||"—"}</td><td>{i.project||i.title||"—"}</td><td className="font-mono text-xs">{i.due_date||"—"}</td><td><Badge>{LABELS[i.ui_status]||i.ui_status}</Badge></td><td>{i.parts?.length||0}</td></tr>)}{!items.length&&<tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">还没有询价单</td></tr>}</tbody></table></Card>
  </div>
}
