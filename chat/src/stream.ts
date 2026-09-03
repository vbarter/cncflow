/** Force OpenAI-compatible chat completions onto the SSE path. tu-zi honors stream. */
export function forceTuziStream(payload: unknown): unknown {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return payload
  return { ...(payload as Record<string, unknown>), stream: true }
}

export function forceTuziStreamFetch(baseFetch: typeof fetch = globalThis.fetch): typeof fetch {
  return async (input, init) => {
    let next = init
    const body = init?.body
    if (typeof body === "string") {
      try {
        next = { ...init, body: JSON.stringify(forceTuziStream(JSON.parse(body))) }
      } catch {
        /* not JSON */
      }
    }
    return baseFetch(input, next)
  }
}
