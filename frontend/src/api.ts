const root = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "")
  || (import.meta.env.BASE_URL as string).replace(/\/$/, "")

export const API = `${root}/api/v1`

export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || r.statusText)
  return data
}
