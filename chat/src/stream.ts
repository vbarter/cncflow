/** Force OpenAI-compatible chat completions onto the SSE path. tu-zi honors stream. */
export function forceTuziStream(payload: unknown): unknown {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return payload
  return { ...(payload as Record<string, unknown>), stream: true }
}

export function forceTuziStreamFetch(baseFetch: typeof fetch = globalThis.fetch): typeof fetch {
  return async (input, init) => {
    const headers = new Headers(init?.headers)
    // This is the compression boundary #135 did not cover. A compressed SSE
    // response can sit in the tu-zi/CDN/undici path until its final gzip block.
    headers.set("Accept-Encoding", "identity")
    headers.set("Cache-Control", "no-cache, no-transform")
    let next = { ...init, headers }
    const body = init?.body
    if (typeof body === "string") {
      try {
        next = { ...next, body: JSON.stringify(forceTuziStream(JSON.parse(body))) }
      } catch {
        /* not JSON */
      }
    }
    return baseFetch(input, next)
  }
}
