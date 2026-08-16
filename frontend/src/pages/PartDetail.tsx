import { useEffect, useState } from "react"
import { Badge, Button, Card, Select } from "../components/ui"
import { json } from "../api"

export function PartDetail({ id, go }:{ id:string; go:(h:string)=>void }) {
  const [part,setPart]=useState<any>(null); const [view,setView]=useState<"eng"|"boss">("eng"); const [err,setErr]=useState("")
  async function load(){ setPart(await json<any>("/parts/"+id)) }
  useEffect(()=>{ load() },[id])
  async function act(path:string){ try{ setPart(await json<any>(path,{method:"POST",body:"{}"})); }catch(e:any){setErr(e.message)} }
  async function slider(v:string){ try{ setPart(await json<any>("/parts/"+id,{method:"PATCH",body:JSON.stringify({slider:v})})) }catch(e:any){setErr(e.message)} }
  if(!part) return <div className="text-sm text-zinc-500">加载中…</div>
  const q=part.quote||{}; const quote=q.quote||{}; const ui=q.ui_cost||{}; const risk=q.risk||{}
  const locked=part.status==="confirmed"
  return <div className="space-y-5">
    <div className="flex items-end justify-between"><div><div className="font-mono text-[10px] uppercase tracking-[.18em] text-zinc-500">Part</div><h1 className="mt-2 text-3xl font-semibold">{part.name}</h1></div>
      <div className="flex gap-2"><Button variant={view==="eng"?"default":"outline"} onClick={()=>setView("eng")}>工程师</Button><Button variant={view==="boss"?"default":"outline"} onClick={()=>setView("boss")}>老板</Button></div></div>
    <div className="grid gap-4 md:grid-cols-3">
      <Card className="p-5"><div className="text-xs text-zinc-500">报价</div><div className="mt-2 text-2xl font-semibold">¥{quote.amount??"—"}</div><div className="mt-1 text-xs text-zinc-500">成本 ¥{quote.cost??"—"} · 毛利 {quote.margin??"—"}%</div></Card>
      <Card className="p-5"><div className="text-xs text-zinc-500">置信度</div><div className="mt-2 text-2xl font-semibold">{q.confidence??"—"}</div><Badge className="mt-2">{risk.level}{risk.customer_forbidden?" · 禁止给客户":""}</Badge></Card>
      <Card className="p-5"><div className="text-xs text-zinc-500">滑轴</div><Select disabled={locked} value={q.slider?.slider||part.slider||"标准"} onChange={e=>slider(e.target.value)} className="mt-2"><option>保守</option><option>偏保守</option><option>标准</option><option>偏激进</option><option>激进</option></Select></Card>
    </div>
    {view==="eng"?<Card className="p-5"><div className="mb-3 font-medium">成本构成 / 特征</div>
      <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">{Object.entries(ui).map(([k,v])=><div key={k}>{k} ¥{String(v)}</div>)}</div>
      <div className="mt-4 text-xs text-zinc-500">风险：{(risk.tags||[]).join("、")||"—"}</div>
      <div className="mt-3 space-y-2 text-sm">{(q.features||[]).map((f:any)=><div key={f.feature_id} className="border-b border-zinc-100 py-2">{f.feature_id} · {f.type} · {f.plan?.difficulty?.level||f.plan?.machinability?.level||""}</div>)}</div>
    </Card>:<Card className="p-5"><div className="font-medium">接单理由</div><p className="mt-3 text-sm leading-6 text-zinc-600">成本 ¥{quote.cost}，报价 ¥{quote.amount}，毛利 {quote.margin}%。风险 {risk.level}。{risk.customer_forbidden?"置信度偏低，不建议直接给客户。":"可内部确认后出给客户。"}</p></Card>}
    <div className="flex gap-3">
      <Button disabled={locked||part.status!=="quoted"} onClick={()=>act("/parts/"+id+"/confirm")}>确认报价</Button>
      <Button variant="outline" disabled={locked} onClick={()=>act("/parts/"+id+"/abandon")}>废弃</Button>
      <Button variant="ghost" onClick={()=>go("inquiry/"+part.inquiry_id)}>回询价单</Button>
    </div>
    {err&&<div className="text-sm text-red-700">{err}</div>}
  </div>
}
