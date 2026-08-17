import { useEffect, useState } from "react"
import { LoaderCircle } from "lucide-react"
import { Card, Progress } from "../components/ui"
import { json } from "../api"

const STEPS = ["读模型","特征公差","工艺 SETUP","匹配设备刀具","算工时成本","综合报价"]
const TERMINAL = new Set(["needs_review", "completed", "failed"])

function stepFromJobs(jobs: any[]) {
  if (!jobs.length) return 0
  if (jobs.some(j => j.status === "failed")) return 0
  const prog = Math.max(...jobs.map(j => Number(j.progress) || 0))
  const stages = jobs.map(j => j.stage || j.status)
  if (jobs.every(j => TERMINAL.has(j.status))) return 2
  if (prog >= 65 || stages.some((s: string) => s === "pdf_drawing")) return 1
  return 0
}

export function Parsing({ id, go }:{ id:string; go:(h:string)=>void }) {
  const [err,setErr]=useState("")
  const [step,setStep]=useState(0)
  useEffect(()=>{
    let stopped = false
    let quoted = false
    const started = Date.now()
    async function tick() {
      try {
        const inq = await json<any>("/inquiries/"+id)
        const parts = inq.parts || []
        const jobIds = parts.map((p: any) => p.parse_job_id).filter(Boolean)
        if (!jobIds.length) {
          if (quoted) return
          quoted = true
          await json<any>(`/inquiries/${id}/quote`, { method: "POST", body: "{}" })
          if (!stopped) { setStep(5); setTimeout(()=>go("inquiry/"+id), 400) }
          return
        }
        const jobs = await Promise.all(jobIds.map((jid: string) => json<any>("/parse-jobs/"+jid)))
        if (stopped) return
        setStep(stepFromJobs(jobs))
        const failed = jobs.find((j: any) => j.status === "failed")
        if (failed) { setErr(failed.error || "解析失败"); return }
        const pending = jobs.filter((j: any) => !TERMINAL.has(j.status))
        if (pending.length) {
          if (Date.now() - started > 180000) { setErr("解析超时，请返回重试"); return }
          return
        }
        if (quoted) return
        quoted = true
        setStep(2)
        await json<any>(`/inquiries/${id}/quote`, { method: "POST", body: "{}" })
        if (stopped) return
        setStep(5)
        setTimeout(()=>go("inquiry/"+id), 400)
      } catch (e: any) {
        if (!stopped) setErr(e.message)
      }
    }
    tick()
    const iv = window.setInterval(tick, 1000)
    return () => { stopped = true; window.clearInterval(iv) }
  }, [id])
  return <Card className="p-5 md:p-8">
    <div className="mb-6 flex items-center gap-3"><LoaderCircle className="animate-spin" size={20}/><div><div className="font-medium">AI 解析中</div><div className="text-xs text-slate-500">{STEPS[step]}</div></div></div>
    <Progress value={(step+1)/6*100}/>
    <div className="mt-4 flex flex-wrap justify-center gap-x-3 gap-y-2 text-center text-[11px] text-slate-500 md:grid md:grid-cols-6 md:gap-2">{STEPS.map((s,i)=><div key={s} className={`min-w-[4.5rem] md:min-w-0 ${i<=step?"text-slate-950":""}`}>{s}</div>)}</div>
    {err&&<div className="mt-4 text-sm text-red-700">解析失败：{err}。可返回重填。</div>}
  </Card>
}
