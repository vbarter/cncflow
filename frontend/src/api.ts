const viteEnv = (import.meta as { env?: { VITE_API_URL?: string; BASE_URL?: string } }).env || {}
const root = viteEnv.VITE_API_URL?.replace(/\/$/, "")
  || (viteEnv.BASE_URL || "").replace(/\/$/, "")

export const API = `${root}/api/v1`

export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || r.statusText)
  return data
}

export async function upload<T>(path: string, form: FormData): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: "POST", body: form })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || r.statusText)
  return data
}
