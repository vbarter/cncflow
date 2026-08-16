import { useEffect, useState } from "react"
import { Badge, Button, Card } from "../components/ui"
import { json } from "../api"

export function InquiryDetail({ id, go }:{ id:string; go:(h:string)=>void }) {
  const [inq,setInq]=useState<any>(null)
  useEffect(()=>{ json<any>("/inquiries/"+id).then(setInq) },[id])
  if(!inq) return <div className="text-sm text-zinc-500">加载中…</div>
  return <div className="space-y-5">
    <div className="flex items-end justify-between"><div><div className="font-mono text-[10px] uppercase tracking-[.18em] text-zinc-500">Inquiry</div><h1 className="mt-2 text-3xl font-semibold">{inq.customer||"询价单"} · {inq.project||"—"}</h1><p className="mt-1 text-sm text-zinc-500">交期 {inq.due_date||"—"}</p></div><Button variant="outline" onClick={()=>go("")}>回工作台</Button></div>
    <div className="grid gap-4 md:grid-cols-2">{inq.parts.map((p:any)=>{
      const q=p.quote?.quote; const risk=p.quote?.risk
      return <Card key={p.id} className="cursor-pointer p-5 hover:border-zinc-400" onClick={()=>go("part/"+p.id)}>
        <div className="flex items-center justify-between"><div className="font-medium">{p.name}</div><Badge>{p.status}</Badge></div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-sm"><div>报价 <span className="font-semibold">¥{q?.amount??"—"}</span></div><div>成本 ¥{q?.cost??"—"}</div><div>毛利 {q?.margin??"—"}%</div><div>风险 {risk?.level||"—"}</div></div>
      </Card>
    })}</div>
  </div>
}
