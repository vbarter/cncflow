import { useEffect, useState } from "react"
import { Badge, Button, Input } from "./components/ui"
import { Workbench } from "./pages/Workbench"
import { NewInquiry } from "./pages/NewInquiry"
import { Parsing } from "./pages/Parsing"
import { InquiryDetail } from "./pages/InquiryDetail"
import { PartDetail } from "./pages/PartDetail"
import { FactoryConfig } from "./pages/FactoryConfig"
import { ParseLegacy } from "./ParseLegacy"
import { API, json } from "./api"

function route(){ return (location.hash.replace(/^#\/?/, "") || "") }

function HeaderSearch({ go }: { go: (h: string) => void }) {
  const [q, setQ] = useState("")
  const [hits, setHits] = useState<any[]>([])
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const t = q.trim()
    if (t.length < 1) { setHits([]); return }
    let stop = false
    json<{ items: any[] }>("/inquiries").then(d => {
      if (stop) return
      const needle = t.toLowerCase()
      const found: any[] = []
      for (const inq of d.items || []) {
        const blob = `${inq.title || ""} ${inq.customer || ""} ${inq.project || ""}`
        const partHit = (inq.parts || []).find((p: any) => (p.name || "").toLowerCase().includes(needle))
        if (blob.toLowerCase().includes(needle) || partHit) {
          found.push({ inq, part: partHit })
        }
      }
      setHits(found.slice(0, 8))
    }).catch(() => setHits([]))
    return () => { stop = true }
  }, [q])
  function pick(h: any) {
    setOpen(false); setQ("")
    go(h.part ? "part/" + h.part.id : "inquiry/" + h.inq.id)
  }
  return <div className="relative hidden md:block">
    <Input
      className="h-9 w-64 text-xs"
      placeholder="搜索询价单、客户或零件"
      value={q}
      onChange={e => { setQ(e.target.value); setOpen(true) }}
      onFocus={() => setOpen(true)}
      onBlur={() => setTimeout(() => setOpen(false), 180)}
      onKeyDown={e => { if (e.key === "Enter" && hits[0]) pick(hits[0]) }}
    />
    {open && q.trim() && (
      <div className="absolute right-0 z-20 mt-1 w-80 rounded border border-[#e2e8f0] bg-white py-1 text-sm shadow-sm">
        {hits.length ? hits.map((h, i) => (
          <button key={i} type="button" className="block w-full px-3 py-2 text-left hover:bg-slate-50" onMouseDown={() => pick(h)}>
            <div className="font-medium text-slate-800">{h.part ? h.part.name : (h.inq.title || "询价单")}</div>
            <div className="text-xs text-slate-400">{h.inq.customer || "—"} · {h.inq.title || ""}</div>
          </button>
        )) : <div className="px-3 py-2 text-xs text-slate-400">没有匹配</div>}
      </div>
    )}
  </div>
}

export function App(){
  const [hash,setHash]=useState(route)
  const [parser,setParser]=useState<boolean|null>(null)
  useEffect(()=>{ const on=()=>setHash(route()); window.addEventListener("hashchange",on); return ()=>window.removeEventListener("hashchange",on) },[])
  useEffect(()=>{ fetch(`${API}/health`).then(r=>r.json()).then(d=>setParser(!!d.parser?.available)).catch(()=>setParser(false)) },[])
  const go=(h:string)=>{ location.hash = h ? "#/"+h : "#/"; setHash(h) }
  const [seg,id] = hash.split("/")
  return <main className="min-h-screen bg-[#f8fafc] text-slate-900">
    <header className="border-b border-[#e2e8f0] bg-white"><div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between px-5">
      <button className="flex items-center gap-3" onClick={()=>go("")}><div className="grid h-8 w-8 place-items-center bg-blue-600 font-mono text-[11px] font-semibold leading-none text-white" style={{clipPath:"polygon(0 0,100% 0,100% 72%,72% 100%,0 100%)"}}>C/</div><div className="text-left leading-tight"><div className="text-[10px] tracking-[.16em] text-slate-400">AI CNC</div><div className="text-sm font-semibold text-slate-900">报价助手</div></div></button>
      <nav className="flex items-center gap-2 text-sm">
        <button className={`h-14 rounded-none border-b-2 px-3 ${seg===""||seg==="new"||seg==="parsing"||seg==="inquiry"||seg==="part"?"border-blue-600 text-blue-600":"border-transparent text-slate-600"}`} onClick={()=>go("")}>报价</button>
        <button className={`h-14 rounded-none border-b-2 px-3 ${seg==="factory"?"border-blue-600 text-blue-600":"border-transparent text-slate-600"}`} onClick={()=>go("factory")}>工厂配置</button>
        <HeaderSearch go={go}/>
        <Button variant="ghost" size="sm" onClick={()=>go("new")}>新建</Button>
        <Button variant="ghost" className="text-slate-500" onClick={()=>go("parse")}>解析子流</Button>
        <Badge className={parser?"border-emerald-200 bg-emerald-50 text-emerald-700":"border-slate-200"}>{parser?"解析在线":"解析离线"}</Badge>
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
