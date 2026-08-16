import { useEffect, useState } from "react"
import { LoaderCircle } from "lucide-react"
import { Card, Progress } from "../components/ui"
import { json } from "../api"

const STEPS = ["读模型","特征公差","工艺 SETUP","匹配设备刀具","算工时成本","综合报价"]

export function Parsing({ id, go }:{ id:string; go:(h:string)=>void }) {
  const [err,setErr]=useState(""); const [step,setStep]=useState(0)
  useEffect(()=>{
    let n=0
    const tick=window.setInterval(()=>setStep(s=>Math.min(s+1,4)),400)
    json<any>(`/inquiries/${id}/quote`,{method:"POST",body:"{}"}).then(()=>{
      setStep(5); window.clearInterval(tick); setTimeout(()=>go("inquiry/"+id),400)
    }).catch(e=>{setErr(e.message); window.clearInterval(tick)})
    return ()=>window.clearInterval(tick)
  },[id])
  return <Card className="p-8">
    <div className="mb-6 flex items-center gap-3"><LoaderCircle className="animate-spin" size={20}/><div><div className="font-medium">AI 解析中</div><div className="text-xs text-zinc-500">{STEPS[step]}</div></div></div>
    <Progress value={(step+1)/6*100}/>
    <div className="mt-4 grid grid-cols-2 gap-2 text-center text-[11px] text-zinc-500 sm:grid-cols-6">{STEPS.map((s,i)=><div key={s} className={i<=step?"text-zinc-950":""}>{s}</div>)}</div>
    {err&&<div className="mt-4 text-sm text-red-700">解析失败：{err}。可返回重填。</div>}
  </Card>
}
