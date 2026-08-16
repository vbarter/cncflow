import { useEffect, useState } from "react"
import { Button, Card, Input } from "../components/ui"
import { json } from "../api"

const TABS = ["基本信息","设备库","刀具库","材料价格","默认规则"]

export function FactoryConfig() {
  const [cfg,setCfg]=useState<any>(null); const [tab,setTab]=useState(0); const [msg,setMsg]=useState("")
  useEffect(()=>{ json<any>("/factory-config").then(setCfg) },[])
  async function save(){ const next=await json<any>("/factory-config",{method:"PUT",body:JSON.stringify(cfg)}); setCfg(next); setMsg("已保存") }
  if(!cfg) return <div className="text-sm text-zinc-500">加载中…</div>
  const s=cfg.settings
  return <div className="space-y-5">
    <div className="flex items-end justify-between"><div><div className="font-mono text-[10px] uppercase tracking-[.18em] text-zinc-500">Factory</div><h1 className="mt-2 text-3xl font-semibold">工厂配置</h1></div><Button onClick={save}>保存</Button></div>
    <div className="flex flex-wrap gap-2">{TABS.map((t,i)=><Button key={t} variant={tab===i?"default":"outline"} onClick={()=>setTab(i)}>{t}</Button>)}</div>
    {tab===0&&<Card className="grid gap-3 p-5 md:grid-cols-3"><label className="text-xs text-zinc-500">利润 %<Input className="mt-1" type="number" value={s.profit_pct} onChange={e=>setCfg({...cfg,settings:{...s,profit_pct:Number(e.target.value)}})}/></label><label className="text-xs text-zinc-500">最低收费<Input className="mt-1" type="number" value={s.floor_charge} onChange={e=>setCfg({...cfg,settings:{...s,floor_charge:Number(e.target.value)}})}/></label><label className="text-xs text-zinc-500">检测费<Input className="mt-1" type="number" value={s.inspect_fee} onChange={e=>setCfg({...cfg,settings:{...s,inspect_fee:Number(e.target.value)}})}/></label><label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={!!s.ignore_available_machines} onChange={e=>setCfg({...cfg,settings:{...s,ignore_available_machines:e.target.checked}})}/>忽略可用设备</label></Card>}
    {tab===1&&<Card className="p-5 text-sm">{(cfg.machines||[]).length?cfg.machines.map((m:any)=><div key={m.id} className="border-b py-2">{m.id} · {m.type} · {m.axes}轴</div>):<p className="text-zinc-500">还没有设备，可在此页保存后用 API 添加。费率见默认规则。</p>}</Card>}
    {tab===2&&<Card className="p-5 text-sm text-zinc-500">刀具勾选对接现有 tools 目录。当前勾选 {cfg.tools?.length||0} 条。</Card>}
    {tab===3&&<Card className="space-y-3 p-5">{(cfg.material_prices||[]).map((m:any,i:number)=><div key={m.material_code} className="grid grid-cols-3 gap-2 text-sm"><div>{m.material_code}</div><Input type="number" value={m.price_per_kg} onChange={e=>{const list=[...cfg.material_prices];list[i]={...m,price_per_kg:Number(e.target.value)};setCfg({...cfg,material_prices:list})}}/><Input type="number" value={m.scrap_price_per_kg} onChange={e=>{const list=[...cfg.material_prices];list[i]={...m,scrap_price_per_kg:Number(e.target.value)};setCfg({...cfg,material_prices:list})}}/></div>)}<Button variant="outline" onClick={()=>setCfg({...cfg,material_prices:[...cfg.material_prices,{material_code:"AL-6061",price_per_kg:28,scrap_price_per_kg:8}]})}>加一条材料价</Button></Card>}
    {tab===4&&<Card className="p-5"><table className="w-full text-left text-sm"><thead><tr className="text-xs text-zinc-500"><th>设备</th><th>机时</th><th>调机</th><th>编程</th></tr></thead><tbody>{cfg.rate_table.map((r:any)=><tr key={r.equipment_type} className="border-b"><td className="py-2">{r.equipment_type}</td><td>¥{r.hourly_rate}</td><td>¥{r.setup_fee}</td><td>¥{r.programming_fee_new}</td></tr>)}</tbody></table></Card>}
    {msg&&<div className="text-sm text-emerald-700">{msg}</div>}
  </div>
}
