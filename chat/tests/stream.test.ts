import assert from "node:assert/strict"
import { createServer } from "node:http"
import type { AddressInfo } from "node:net"
import test from "node:test"
import { getRequestListener } from "@hono/node-server"
import { Hono } from "hono"
import type { Agent } from "@earendil-works/pi-agent-core"
import { piToUIMessageResponse, STREAM_HEADERS } from "../src/bridge.ts"
import { forceTuziStream, forceTuziStreamFetch } from "../src/stream.ts"

function fakeAgent(delayMs = 180) {
  const listeners = new Set<(event: unknown) => void>()
  let promptDone = false
  let aborted = false
  let wake: (() => void) | undefined
  const emit = (event: unknown) => {
    for (const listener of listeners) listener(event)
  }
  const agent = {
    promptDone: () => promptDone,
    aborted: () => aborted,
    subscribe(fn: (event: unknown) => void) {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    async prompt() {
      emit({
        type: "message_update",
        assistantMessageEvent: { type: "text_delta", delta: "孔" },
      })
      await new Promise<void>((resolve) => {
        wake = resolve
        setTimeout(resolve, delayMs)
      })
      if (aborted) throw new Error("aborted")
      emit({
        type: "message_update",
        assistantMessageEvent: { type: "text_delta", delta: "工艺链" },
      })
      promptDone = true
    },
    abort() {
      aborted = true
      wake?.()
    },
    state: { messages: [], tools: [] },
  }
  return agent as typeof agent & Agent
}

test("stream headers skip Hono Content-Length buffering and CF gzip", () => {
  assert.equal(STREAM_HEADERS["Transfer-Encoding"], "chunked")
  assert.equal(STREAM_HEADERS["Content-Encoding"], "identity")
  assert.match(STREAM_HEADERS["Content-Type"], /text\/event-stream/)
  assert.equal(STREAM_HEADERS["X-Accel-Buffering"], "no")
  assert.match(STREAM_HEADERS["Cache-Control"], /no-transform/)
  assert.equal("Content-Length" in STREAM_HEADERS, false)
})

test("forceTuziStream rewrites stream:false so tu-zi cannot collapse to one blob", async () => {
  assert.deepEqual(forceTuziStream({ model: "gpt-4.1-mini", stream: false }), {
    model: "gpt-4.1-mini",
    stream: true,
  })
  let seen = ""
  const wrapped = forceTuziStreamFetch(async (_input, init) => {
    seen = String(init?.body || "")
    return new Response("{}", { headers: { "Content-Type": "application/json" } })
  })
  await wrapped("https://api.tu-zi.com/v1/chat/completions", {
    method: "POST",
    body: JSON.stringify({ model: "gpt-4.1-mini", stream: false, messages: [] }),
  })
  assert.equal(JSON.parse(seen).stream, true)
})

test("piToUIMessageResponse yields first SSE chunk before agent.prompt finishes", async () => {
  const agent = fakeAgent(200)
  const response = piToUIMessageResponse(agent, "孔工艺链")
  assert.match(response.headers.get("content-type") || "", /text\/event-stream/)
  assert.equal(response.headers.get("content-length"), null)
  assert.equal(response.headers.get("content-encoding"), "identity")
  assert.equal(response.headers.get("transfer-encoding"), "chunked")

  const reader = response.body?.getReader()
  assert.ok(reader)
  const first = await reader.read()
  const text = new TextDecoder().decode(first.value)
  assert.ok(text.length > 0, "expected a chunk")
  assert.match(text, /data:/)
  assert.doesNotMatch(text.trim(), /^\{/)
  assert.equal(agent.promptDone(), false, "first chunk arrived while prompt still running")
  assert.match(text, /孔/)

  while (!(await reader.read()).done) {
    /* drain */
  }
  assert.equal(agent.promptDone(), true)
})

test("Node HTTP listener flushes first chunk before the agent finishes", async () => {
  const agent = fakeAgent(250)
  const app = new Hono()
  app.post("/api/v1/chat", (c) =>
    piToUIMessageResponse(agent, "孔工艺链", c.req.raw.signal, c.env?.outgoing),
  )

  const server = createServer(getRequestListener(app.fetch))
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve))
  const { port } = server.address() as AddressInfo

  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", parts: [{ type: "text", text: "孔工艺链" }] }],
      }),
    })
    assert.equal(response.ok, true)
    assert.equal(response.headers.get("content-length"), null)
    assert.match(response.headers.get("content-type") || "", /event-stream/)

    const reader = response.body?.getReader()
    assert.ok(reader)
    const first = await reader.read()
    const text = new TextDecoder().decode(first.value)
    assert.match(text, /data:/)
    assert.equal(agent.promptDone(), false, "HTTP first bytes must precede agent finish")
    assert.match(text, /孔/)

    while (!(await reader.read()).done) {
      /* drain */
    }
    assert.equal(agent.promptDone(), true)
  } finally {
    await new Promise<void>((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())))
  }
})

test("createChatApp HTTP handler streams before the agent finishes", async () => {
  process.env.CHAT_NO_LISTEN = "1"
  process.env.TUZI_API_KEY = process.env.TUZI_API_KEY || "test-key"
  const { createChatApp } = await import("../src/server.ts")
  const agent = fakeAgent(250)
  const app = createChatApp({ createAgent: () => agent })
  const server = createServer(getRequestListener(app.fetch))
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve))
  const { port } = server.address() as AddressInfo

  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", parts: [{ type: "text", text: "孔工艺链" }] }],
      }),
    })
    assert.equal(response.ok, true)
    assert.equal(response.headers.get("content-length"), null)
    const reader = response.body?.getReader()
    assert.ok(reader)
    const first = await reader.read()
    const text = new TextDecoder().decode(first.value)
    assert.match(text, /data:/)
    assert.equal(agent.promptDone(), false)
    assert.match(text, /孔/)
    while (!(await reader.read()).done) {
      /* drain */
    }
  } finally {
    await new Promise<void>((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())))
  }
})

test("abort during stream calls agent.abort", async () => {
  const agent = fakeAgent(5_000)
  const ac = new AbortController()
  const response = piToUIMessageResponse(agent, "stop", ac.signal)
  const reader = response.body?.getReader()
  assert.ok(reader)
  await reader.read()
  ac.abort()
  while (!(await reader.read()).done) {
    /* drain */
  }
  assert.equal(agent.aborted(), true)
})
