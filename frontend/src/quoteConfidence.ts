export const EMPTY_DEDUCTION_TEXT = "无扣分项"

export const DIMENSION_LABEL: Record<string, string> = {
  D1: "工时边界",
  D2: "材料去除率",
  D3: "成本比例",
  D4: "设备匹配",
  D5: "切削参数",
  D6: "工序顺序",
  D7: "材料成本",
  D8: "数据一致性",
  D9: "关键字段",
}

const CATEGORY_DEFINITIONS = [
  { key: "drawing", label: "图纸识别", dimensions: ["D9"] },
  { key: "process", label: "工艺可加工性", dimensions: ["D1", "D2", "D5", "D6"] },
  { key: "factory", label: "工厂资源匹配", dimensions: ["D4"] },
  { key: "cost", label: "成本数据完整性", dimensions: ["D3", "D7", "D8"] },
] as const

type CategoryKey = (typeof CATEGORY_DEFINITIONS)[number]["key"]

export type ConfidenceDeduction = {
  ruleId: string
  dimension: string
  reason: string
  deduction: number
}

export type ConfidenceColumn = {
  key: CategoryKey
  label: string
  score: number
  deductions: ConfidenceDeduction[]
}

function dimensionOf(item: Record<string, unknown>) {
  const explicit = String(item.dimension || "").toUpperCase()
  if (/^D[1-9]$/.test(explicit)) return explicit
  return String(item.rule_id || "").toUpperCase().match(/^(D[1-9])(?:-|$)/)?.[1] || ""
}

function categoryOf(reason: string, dimension: string) {
  const is2DMissingField = /2D.*(?:未提供|未给|缺少|缺失|未标注|未填写|未识别|无(?:局部)?公差)/i.test(reason)
  if (is2DMissingField) return "drawing"

  const isToolAccessibility = /(?:刀具.*可达|可达性.*刀具|tool[-\s]?access)/i.test(reason)
  if (isToolAccessibility) return "process"

  return CATEGORY_DEFINITIONS.find((category) =>
    (category.dimensions as readonly string[]).includes(dimension)
  )?.key
}

function normalizeDeduction(value: unknown) {
  if (value == null || value === "") return null
  const deduction = Math.abs(Number(value))
  return Number.isFinite(deduction) ? deduction : null
}

export function formatDeduction(deduction: number) {
  return `−${deduction}`
}

export function liveConfidenceValue(value: unknown) {
  if (value == null || value === "") return null
  const confidence = Number(value)
  return Number.isFinite(confidence) ? confidence : null
}

export function confidenceColumns(rawDeductions: unknown): ConfidenceColumn[] {
  const grouped = new Map<CategoryKey, ConfidenceDeduction[]>()
  for (const category of CATEGORY_DEFINITIONS) grouped.set(category.key, [])

  if (Array.isArray(rawDeductions)) {
    for (const rawItem of rawDeductions) {
      if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) continue
      const item = rawItem as Record<string, unknown>
      const deduction = normalizeDeduction(item.deduction)
      if (deduction == null) continue

      const dimension = dimensionOf(item)
      const reason = String(item.reason || item.rule_id || "—")
      const category = categoryOf(reason, dimension)
      if (!category) continue

      grouped.get(category)?.push({
        ruleId: String(item.rule_id || ""),
        dimension,
        reason,
        deduction,
      })
    }
  }

  return CATEGORY_DEFINITIONS.map(({ key, label }) => {
    const deductions = grouped.get(key) || []
    const totalDeduction = deductions.reduce((total, item) => total + item.deduction, 0)
    return {
      key,
      label,
      deductions,
      score: Math.max(0, 100 - totalDeduction),
    }
  })
}
