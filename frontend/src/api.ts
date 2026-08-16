export const API = import.meta.env.BASE_URL.replace(/\/$/, "") + "/api/v1"

export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || r.statusText)
  return data
}
