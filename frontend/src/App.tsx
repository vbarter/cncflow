import { useEffect, useState } from "react"
import { Badge, Button } from "./components/ui"
import { Workbench } from "./pages/Workbench"
import { NewInquiry } from "./pages/NewInquiry"
import { Parsing } from "./pages/Parsing"
import { InquiryDetail } from "./pages/InquiryDetail"
import { PartDetail } from "./pages/PartDetail"
import { FactoryConfig } from "./pages/FactoryConfig"
import { ParseLegacy } from "./ParseLegacy"
import { API } from "./api"

function route(){ return (location.hash.replace(/^#\/?/, "") || "") }

export function App(){
  const [hash,setHash]=useState(route)
  const [parser,setParser]=useState<boolean|null>(null)
  useEffect(()=>{ const on=()=>setHash(route()); window.addEventListener("hashchange",on); return ()=>window.removeEventListener("hashchange",on) },[])
  useEffect(()=>{ fetch(`${API}/health`).then(r=>r.json()).then(d=>setParser(!!d.parser?.available)).catch(()=>setParser(false)) },[])
  const go=(h:string)=>{ location.hash = h ? "#/"+h : "#/"; setHash(h) }
  const [seg,id] = hash.split("/")
  return <main className="min-h-screen bg-[#f8fafc] text-slate-900">
    <header className="border-b border-[#e2e8f0] bg-white"><div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-5">
      <button className="flex items-center gap-3" onClick={()=>go("")}><div className="grid h-8 w-8 place-items-center bg-blue-600 font-mono text-[11px] font-semibold leading-none text-white" style={{clipPath:"polygon(0 0,100% 0,100% 72%,72% 100%,0 100%)"}}>C/</div><div className="text-left"><div className="text-sm font-semibold">C/AI CNC</div><div className="text-[10px] tracking-[.18em] text-slate-500">报价助手</div></div></button>
      <nav className="flex items-center gap-2 text-sm">
        <button className={`h-14 px-3 ${seg===""||seg==="new"||seg==="parsing"||seg==="inquiry"||seg==="part"?"border-b-2 border-blue-600 text-blue-600":"text-slate-600"}`} onClick={()=>go("")}>报价</button>
        <button className={`h-14 px-3 ${seg==="factory"?"border-b-2 border-blue-600 text-blue-600":"text-slate-600"}`} onClick={()=>go("factory")}>工厂配置</button>
        <Button variant="ghost" size="sm" onClick={()=>go("new")}>新建</Button>
        <button className="px-2 text-xs text-slate-400 hover:text-slate-600" onClick={()=>go("parse")}>解析子流</button>
        <Badge className={parser?"border-emerald-200 bg-emerald-50 text-emerald-700":"border-zinc-200"}>{parser?"解析在线":"解析离线"}</Badge>
      </nav>
    </div></header>
    <div className="mx-auto max-w-[1440px] px-5 py-8">
      {seg===""&&<Workbench go={go}/>}
      {seg==="new"&&<NewInquiry go={go}/>}
      {seg==="parsing"&&id&&<Parsing id={id} go={go}/>}
      {seg==="inquiry"&&id&&<InquiryDetail id={id} go={go}/>}
      {seg==="part"&&id&&<PartDetail id={id} go={go}/>}
      {seg==="factory"&&<FactoryConfig/>}
      {seg==="parse"&&<ParseLegacy/>}
    </div>
  </main>
}
