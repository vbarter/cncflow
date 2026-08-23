import { useEffect, useState } from "react"
import { ParseProgress } from "../components/ParseProgress"
import { json } from "../api"
import {
  isParseJobTerminal,
  parseStepFromJobs,
  type ParseJobProgress,
} from "../parseProgress"

type ParseJob = ParseJobProgress & { job_id: string }

const wait = (milliseconds: number) => new Promise(resolve => window.setTimeout(resolve, milliseconds))

export function Parsing({ id, go }:{ id:string; go:(h:string)=>void }) {
  const [step, setStep] = useState(0)
  const [failed, setFailed] = useState(false)
  const [failedJobIds, setFailedJobIds] = useState<string[]>([])
  const [retrying, setRetrying] = useState(false)
  const [pollError, setPollError] = useState("")
  const [cycle, setCycle] = useState(0)

  useEffect(()=>{
    let stopped = false
    let quoted = false
    let halted = false
    let inFlight = false

    async function quoteWithStagedProgress() {
      setStep(2)
      const quoteResult = json<any>(`/inquiries/${id}/quote`, {
        method: "POST",
        body: "{}",
      }).then(
        value => ({ value, error: null }),
        error => ({ value: null, error: error as Error }),
      )

      await wait(350)
      if (stopped) return false
      setStep(3)
      await wait(350)
      if (stopped) return false
      setStep(4)

      const outcome = await quoteResult
      if (stopped) return false
      if (outcome.error) {
        quoted = false
        setPollError(outcome.error.message)
        return false
      }

      setPollError("")
      setStep(5)
      await wait(450)
      if (!stopped) go("inquiry/" + id)
      return true
    }

    async function tick() {
      if (stopped || halted || inFlight) return
      inFlight = true
      try {
        const inq = await json<any>("/inquiries/"+id)
        const parts = inq.parts || []
        const jobIds = parts.map((p: any) => p.parse_job_id).filter(Boolean)
        if (!jobIds.length) {
          if (quoted) return
          quoted = true
          await quoteWithStagedProgress()
          return
        }
        const jobs = await Promise.all(
          jobIds.map((jid: string) => json<ParseJob>("/parse-jobs/" + jid)),
        )
        if (stopped) return
        setPollError("")
        setStep(parseStepFromJobs(jobs))
        const failedJobs = jobs.filter(job => job.status === "failed")
        if (failedJobs.length) {
          halted = true
          setFailedJobIds(failedJobs.map(job => job.job_id))
          setFailed(true)
          return
        }
        const pending = jobs.filter(job => !isParseJobTerminal(job))
        if (pending.length) return
        if (quoted) return
        quoted = true
        await quoteWithStagedProgress()
      } catch (e: any) {
        if (!stopped) setPollError(e.message)
      } finally {
        inFlight = false
      }
    }

    setFailed(false)
    setFailedJobIds([])
    setPollError("")
    setStep(0)
    tick()
    const iv = window.setInterval(tick, 1000)
    return () => { stopped = true; window.clearInterval(iv) }
  }, [cycle, id])

  async function retry() {
    if (!failedJobIds.length || retrying) return
    setRetrying(true)
    try {
      await Promise.all(failedJobIds.map(jobId => json(`/parse-jobs/${jobId}/retry`, {
        method: "POST",
        body: "{}",
      })))
      setCycle(value => value + 1)
    } catch (error: any) {
      setPollError(error.message)
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div>
      <ParseProgress
        currentStep={step}
        failed={failed}
        retrying={retrying}
        onRetry={retry}
      />
      {pollError && (
        <p className="mt-3 text-center text-xs text-red-700" role="status">
          {pollError}
        </p>
      )}
    </div>
  )
}
