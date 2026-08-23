import { Check, LoaderCircle, RotateCcw, TriangleAlert } from "lucide-react"
import { PARSE_FAILURE, PARSE_STEPS } from "../parseProgress"
import { Button, Card, Progress } from "./ui"

type ParseProgressProps = {
  currentStep: number
  failed?: boolean
  retrying?: boolean
  onRetry?: () => void
}

export function ParseProgress({
  currentStep,
  failed = false,
  retrying = false,
  onRetry,
}: ParseProgressProps) {
  if (failed) {
    return (
      <Card className="px-5 py-12 md:px-8 md:py-16">
        <div className="mx-auto flex max-w-md flex-col items-center text-center">
          <div className="grid h-12 w-12 place-items-center rounded bg-red-50 text-red-600">
            <TriangleAlert size={22} aria-hidden="true" />
          </div>
          <h1 className="mt-5 text-xl font-semibold text-slate-950">{PARSE_FAILURE.title}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">{PARSE_FAILURE.body}</p>
          <Button className="mt-7 min-w-28" onClick={onRetry} disabled={retrying}>
            {retrying
              ? <LoaderCircle className="mr-2 animate-spin" size={16} aria-hidden="true" />
              : <RotateCcw className="mr-2" size={16} aria-hidden="true" />}
            {PARSE_FAILURE.action}
          </Button>
        </div>
      </Card>
    )
  }

  const boundedStep = Math.max(0, Math.min(currentStep, PARSE_STEPS.length - 1))
  const progress = boundedStep / (PARSE_STEPS.length - 1) * 100

  return (
    <Card className="p-5 md:p-8">
      <div className="mb-7 flex items-center gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded bg-blue-50 text-blue-600">
          <LoaderCircle className="animate-spin" size={20} aria-hidden="true" />
        </div>
        <div>
          <h1 className="font-medium text-slate-950">AI 解析中</h1>
          <p className="mt-0.5 text-xs text-slate-500">{PARSE_STEPS[boundedStep]}</p>
        </div>
      </div>

      <Progress value={progress} />
      <ol className="mt-6 grid gap-3 md:grid-cols-6 md:gap-2">
        {PARSE_STEPS.map((label, index) => {
          const state = index < boundedStep ? "completed" : index === boundedStep ? "current" : "pending"
          return (
            <li
              key={label}
              data-state={state}
              aria-current={state === "current" ? "step" : undefined}
              className="flex items-center gap-3 md:flex-col md:gap-2 md:text-center"
            >
              <span
                className={`grid h-7 w-7 shrink-0 place-items-center rounded border text-[11px] font-semibold transition-colors ${
                  state === "completed"
                    ? "border-blue-600 bg-blue-600 text-white"
                    : state === "current"
                      ? "border-blue-600 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-400"
                }`}
              >
                {state === "completed" ? <Check size={14} aria-hidden="true" /> : index + 1}
              </span>
              <span className={`text-xs leading-5 ${
                state === "pending" ? "text-slate-400" : "font-medium text-slate-900"
              }`}>
                {label}
              </span>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}
