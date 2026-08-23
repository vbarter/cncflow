export const PARSE_STEPS = [
  "读模型",
  "特征公差",
  "工艺 SETUP",
  "匹配设备刀具",
  "算工时成本",
  "综合报价",
] as const

export const PARSE_FAILURE = {
  title: "解析失败",
  body: "模型未能完成解析，请检查 STEP 后重试",
  action: "重试",
} as const

export type ParseJobProgress = {
  status: string
  stage?: string | null
  progress?: number | null
}

const TERMINAL_STATUSES = new Set(["needs_review", "completed"])
const FEATURE_STAGES = new Set(["pdf_drawing", "review", "completed"])

export function isParseJobTerminal(job: ParseJobProgress) {
  return TERMINAL_STATUSES.has(job.status)
}

export function parseStepFromJobs(jobs: ParseJobProgress[]) {
  if (!jobs.length) return 2
  if (jobs.every(isParseJobTerminal)) return 2

  const slowestStep = Math.min(...jobs.map(job => {
    const progress = Number(job.progress) || 0
    const stage = job.stage || job.status
    return progress >= 65 || FEATURE_STAGES.has(stage) ? 1 : 0
  }))

  return slowestStep
}
