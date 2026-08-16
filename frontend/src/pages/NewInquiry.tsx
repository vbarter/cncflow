import { useState } from "react"
import { Button, Card, Input, Select } from "../components/ui"
import { json } from "../api"

type PartDraft = { name:string; qty:string; material:string; blank_type:string; length:string; width:string; height:string; surface_finish:string; tolerance_it:string; roughness_ra:string; is_repeat_order:boolean }

const empty: PartDraft = { name:"", qty:"1", material:"铝合金", blank_type:"板料", length:"80", width:"60", height:"20", surface_finish:"", tolerance_it:"11", roughness_ra:"3.2", is_repeat_order:false }

export function NewInquiry({ go }:{ go:(h:string)=>void }) {
  const [customer,setCustomer]=useState(""); const [project,setProject]=useState(""); const [due,setDue]=useState("")
  const [parts,setParts]=useState<PartDraft[]>([{...empty}])
  const [err,setErr]=useState(""); const [busy,setBusy]=useState(false)
  function upd(i:number,k:keyof PartDraft,v:any){setParts(p=>p.map((x,idx)=>idx===i?{...x,[k]:v}:x))}
  async function submit(){
    setErr(""); setBusy(true)
    try{
      const inq = await json<any>("/inquiries",{method:"POST",body:JSON.stringify({customer,project,due_date:due,title:project})})
      for(const p of parts){
        await json(`/inquiries/${inq.id}/parts`,{method:"POST",body:JSON.stringify({
          name:p.name||"零件", qty:Number(p.qty)||1, material:p.material, blank_type:p.blank_type,
          length:Number(p.length), width:Number(p.width), height:Number(p.height),
          surface_finish:p.surface_finish, tolerance_it:Number(p.tolerance_it), roughness_ra:Number(p.roughness_ra),
          is_repeat_order:p.is_repeat_order, batch_size:Number(p.qty)||1,
        })})
      }
      go("parsing/"+inq.id)
    }catch(e:any){setErr(e.message)} finally{setBusy(false)}
  }
  return <div className="space-y-6">
    <div><div className="font-mono text-[10px] uppercase tracking-[.18em] text-zinc-500">New quote</div><h1 className="mt-2 text-3xl font-semibold">新建报价</h1></div>
    <Card className="grid gap-4 p-5 md:grid-cols-3"><label className="text-xs text-zinc-500">客户<Input className="mt-1" value={customer} onChange={e=>setCustomer(e.target.value)}/></label><label className="text-xs text-zinc-500">项目<Input className="mt-1" value={project} onChange={e=>setProject(e.target.value)}/></label><label className="text-xs text-zinc-500">交期<Input className="mt-1" type="date" value={due} onChange={e=>setDue(e.target.value)}/></label></Card>
    {parts.map((p,i)=><Card key={i} className="grid gap-3 p-5 md:grid-cols-4">
      <label className="text-xs text-zinc-500">零件名<Input className="mt-1" value={p.name} onChange={e=>upd(i,"name",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">数量<Input className="mt-1" type="number" value={p.qty} onChange={e=>upd(i,"qty",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">材料<Select className="mt-1" value={p.material} onChange={e=>upd(i,"material",e.target.value)}><option>铝合金</option><option>钢</option><option>不锈钢</option><option>钛合金</option><option>淬硬钢</option></Select></label>
      <label className="text-xs text-zinc-500">毛坯<Select className="mt-1" value={p.blank_type} onChange={e=>upd(i,"blank_type",e.target.value)}><option>板料</option><option>棒料</option></Select></label>
      <label className="text-xs text-zinc-500">长 mm<Input className="mt-1" value={p.length} onChange={e=>upd(i,"length",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">宽/直径 mm<Input className="mt-1" value={p.width} onChange={e=>upd(i,"width",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">高 mm<Input className="mt-1" value={p.height} onChange={e=>upd(i,"height",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">表面处理<Input className="mt-1" value={p.surface_finish} onChange={e=>upd(i,"surface_finish",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">IT<Input className="mt-1" value={p.tolerance_it} onChange={e=>upd(i,"tolerance_it",e.target.value)}/></label>
      <label className="text-xs text-zinc-500">Ra<Input className="mt-1" value={p.roughness_ra} onChange={e=>upd(i,"roughness_ra",e.target.value)}/></label>
      <label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={p.is_repeat_order} onChange={e=>upd(i,"is_repeat_order",e.target.checked)}/>翻单</label>
    </Card>)}
    <div className="flex gap-3"><Button variant="outline" onClick={()=>setParts(p=>[...p,{...empty}])}>再加零件</Button><Button onClick={submit} disabled={busy}>{busy?"提交中":"开始报价"}</Button><Button variant="ghost" onClick={()=>go("")}>取消</Button></div>
    {err&&<div className="text-sm text-red-700">{err}</div>}
  </div>
}
