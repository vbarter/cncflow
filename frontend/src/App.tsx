import { useEffect, useState } from "react"
import { CircleDotDashed } from "lucide-react"
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
  return <main className="min-h-screen bg-[#f7f7f5] text-zinc-950">
    <header className="border-b border-zinc-200 bg-white"><div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-5">
      <button className="flex items-center gap-3" onClick={()=>go("")}><div className="grid h-8 w-8 place-items-center bg-zinc-950 text-white"><CircleDotDashed size={18}/></div><div className="text-left"><div className="text-sm font-semibold">CNCFlow</div><div className="text-[10px] uppercase tracking-[.18em] text-zinc-500">Quote MVP</div></div></button>
      <nav className="flex items-center gap-2 text-sm">
        <Button variant="ghost" onClick={()=>go("")}>工作台</Button>
        <Button variant="ghost" onClick={()=>go("new")}>新建</Button>
        <Button variant="ghost" onClick={()=>go("factory")}>工厂配置</Button>
        <Button variant="ghost" onClick={()=>go("parse")}>解析子流</Button>
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
