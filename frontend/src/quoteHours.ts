/** 加工时间：切削+换刀+装夹+空走，不含调机费。优先用引擎 hours，旧单从 cost_items 回推。 */
export function quoteHours(q: any): number | null {
  if (!q) return null
  const direct = q.quote?.hours ?? q.hours?.total
  if (direct != null && Number.isFinite(Number(direct))) return Number(direct)
  const items = q.cost_items || []
  const map: Record<string, number> = {}
  for (const i of items) map[String(i.code)] = Number(i.amount) || 0
  const rate = Number(q.equipment?.hourly_rate) || 0
  if (!rate) return null
  const fee = (map.CUT || 0) + (map.TOOLCHG || 0) + (map.SETUP || 0) + (map.RAPID || 0)
  return Math.round((fee / rate) * 10) / 10
}

export function hoursLabel(h: number | null | undefined) {
  if (h == null || !Number.isFinite(Number(h))) return "—"
  return `${Number(h).toFixed(1)}h`
}
