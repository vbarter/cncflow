export function quoteSuggestedDays(quote: any): number | null {
  const days = Number(quote?.suggested_days)
  return Number.isInteger(days) && days > 0 ? days : null
}

export function inquirySuggestedDays(parts: any[]): number | null {
  const days = (parts || [])
    .map((part) => quoteSuggestedDays(part?.quote))
    .filter((value): value is number => value != null)
  return days.length ? Math.max(...days) : null
}

export function suggestedDaysLabel(days: number | null): string {
  return days == null ? "—" : `${days} 天`
}
