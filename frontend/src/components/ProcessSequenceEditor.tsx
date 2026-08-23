import { useEffect, useState } from "react"
import { Button } from "./ui"

const PROCESS_NAME: Record<string, string> = {
  spot_drill: "点钻",
  drill: "钻孔",
  gun_drill: "枪钻",
  u_drill: "U钻",
  ream: "铰孔",
  bore: "镗孔",
  tap: "攻丝",
  chamfer: "倒角",
  face: "铣面",
  mill: "铣削",
}

const FIELDS = ["minutes", "n", "f", "cut", "passes"] as const
type Field = typeof FIELDS[number]

function valueOf(step: any, field: Field) {
  const value = step[field] ?? step.time?.[field]
  return value == null ? "" : String(value)
}

function formulaLine(step: any) {
  const time = step.time || {}
  const bits = [
    step.formula ?? time.formula,
    `t_min=${step.t_min ?? time.t_min ?? "—"}`,
    `t_max=${step.t_max ?? time.t_max ?? "—"}`,
    step.status ?? time.status ?? "ok",
  ]
  return bits.filter(Boolean).join(" ")
}

export function ProcessStepParameters({
  step,
  locked,
  busy,
  onPatch,
  showFormula = true,
  compact = false,
}: {
  step: any
  locked: boolean
  busy: boolean
  onPatch: (body: object) => Promise<void>
  showFormula?: boolean
  compact?: boolean
}) {
  const [drafts, setDrafts] = useState<Partial<Record<Field, string>>>({})

  useEffect(() => {
    setDrafts({})
  }, [step])

  async function commit(field: Field) {
    const raw = drafts[field]
    if (raw == null) return
    const trimmed = raw.trim()
    await onPatch({
      steps: [{
        step_id: step.step_id,
        [field]: trimmed === "" ? null : Number(trimmed),
      }],
    })
  }

  return <>
    <div className={`grid grid-cols-2 gap-2 ${compact ? "" : "md:grid-cols-5"}`}>
      {FIELDS.map((field) => <label key={field} className="text-xs text-slate-500">
        <span>{field}</span>
        <input
          className="mt-1 w-full rounded border border-[#e2e8f0] px-2 py-1.5 text-sm text-slate-900 disabled:bg-[#f8fafc]"
          type="number"
          min={field === "passes" ? 1 : 0.0001}
          step={field === "passes" ? 1 : "any"}
          disabled={locked || busy}
          value={drafts[field] ?? valueOf(step, field)}
          onChange={(event) => setDrafts((current) => ({
            ...current,
            [field]: event.target.value,
          }))}
          onBlur={() => commit(field)}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur()
          }}
        />
      </label>)}
    </div>
    {showFormula && <div className="mt-2 font-mono text-[11px] text-slate-500">{formulaLine(step)}</div>}
  </>
}

export function ProcessSequenceEditor({
  sequence,
  hasOverrides,
  locked,
  busy,
  onPatch,
}: {
  sequence: any[]
  hasOverrides: boolean
  locked: boolean
  busy: boolean
  onPatch: (body: object) => Promise<void>
}) {
  async function move(index: number, delta: number) {
    const target = index + delta
    if (target < 0 || target >= sequence.length) return
    const reordered = [...sequence]
    ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
    await onPatch({
      steps: reordered.map((step, order) => ({ step_id: step.step_id, order: order + 1 })),
    })
  }

  if (!sequence.length) return <div className="text-sm text-slate-400">暂无工序。改滑轴会触发重算。</div>

  return <div>
    <div className="mb-3 flex items-center justify-between gap-3">
      <div className="text-xs text-slate-500">改序或改参后立即重算报价、扣分与置信度</div>
      <Button
        type="button"
        variant="outline"
        disabled={locked || busy || !hasOverrides}
        onClick={() => onPatch({ reset: true })}
      >
        恢复推荐方案
      </Button>
    </div>
    <div className="space-y-2">
      {sequence.map((step, index) => {
        const stepId = step.step_id
        const name = step.name || PROCESS_NAME[step.process] || step.op || step.process || step.feature_id || "工序"
        return <div key={stepId} className="rounded border border-[#e2e8f0] p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-16 text-slate-500">STEP {String(step.order || index + 1).padStart(2, "0")}</span>
            <span className="min-w-28 flex-1 font-medium">{name}</span>
            <span className="text-xs text-slate-500">{step.sku || step.tool || step.cycle || "—"}</span>
            <button
              type="button"
              className="rounded border px-2 py-1 disabled:opacity-40"
              aria-label={`${name}上移`}
              disabled={locked || busy || index === 0}
              onClick={() => move(index, -1)}
            >↑</button>
            <button
              type="button"
              className="rounded border px-2 py-1 disabled:opacity-40"
              aria-label={`${name}下移`}
              disabled={locked || busy || index === sequence.length - 1}
              onClick={() => move(index, 1)}
            >↓</button>
            <span className="w-16 text-right">¥{Number(step.amount || 0).toFixed(0)}</span>
          </div>
          <div className="mt-3">
            <ProcessStepParameters
              step={step}
              locked={locked}
              busy={busy}
              onPatch={onPatch}
            />
          </div>
        </div>
      })}
    </div>
  </div>
}
