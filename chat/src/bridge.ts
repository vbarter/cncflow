import type { ServerResponse } from "node:http"
import { createUIMessageStream, type UIMessageChunk } from "ai"
import type { Agent } from "@earendil-works/pi-agent-core"

/**
 * Headers that stop @hono/node-server from buffering (it assigns Content-Length
 * unless Transfer-Encoding is chunked) and stop Cloudflare/gzip from waiting for EOS.
 */
export const STREAM_HEADERS: Record<string, string> = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
  "Content-Encoding": "identity",
  "Transfer-Encoding": "chunked",
  "x-vercel-ai-ui-message-stream": "v1",
}

const ALREADY_SENT = "x-hono-already-sent"

function streamHeaders(extra?: Headers): Headers {
  const headers = new Headers(extra)
  for (const [name, value] of Object.entries(STREAM_HEADERS)) {
    headers.set(name, value)
  }
  return headers
}

/**
 * Hold protocol-only frames until the first real assistant text delta, then
 * serialize that prelude and text into one body chunk. There is no timer or
 * text slicing: every later chunk keeps the timing supplied by the agent.
 */
export function textFirstSseStream(
  stream: ReadableStream<UIMessageChunk>,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let pending = ""
  let textStarted = false
  const frame = (chunk: UIMessageChunk) => `data: ${JSON.stringify(chunk)}\n\n`

  return stream.pipeThrough(new TransformStream<UIMessageChunk, Uint8Array>({
    transform(chunk, controller) {
      const encoded = frame(chunk)
      if (!textStarted) {
        pending += encoded
        if (chunk.type !== "text-delta" || chunk.delta.length === 0) return
        textStarted = true
        controller.enqueue(encoder.encode(pending))
        pending = ""
        return
      }
      controller.enqueue(encoder.encode(encoded))
    },
    flush(controller) {
      if (pending) controller.enqueue(encoder.encode(pending))
      controller.enqueue(encoder.encode("data: [DONE]\n\n"))
    },
  }))
}

function pipeTextFirstSseToNode(
  response: ServerResponse,
  stream: ReadableStream<Uint8Array>,
  headers: Headers,
): void {
  void (async () => {
    const reader = stream.getReader()
    let headersSent = false
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        if (!headersSent) {
          response.writeHead(200, Object.fromEntries(headers.entries()))
          headersSent = true
        }
        const socket = response.socket
        const corkedBefore = socket?.writableCorked ?? 0
        response.write(value)
        // ServerResponse auto-corks every write until nextTick. Pi can publish
        // several provider deltas through promise microtasks before that tick,
        // collapsing their HTTP writes into one socket writev. End only the
        // auto-cork opened by this write; preserve any outer/manual cork.
        if (socket && socket === response.socket && socket.writableCorked > corkedBefore) {
          socket.uncork()
        }
      }
      if (!headersSent) response.writeHead(200, Object.fromEntries(headers.entries()))
      response.end()
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error))
      if (!response.headersSent) {
        response.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" })
        response.end(`Error: ${err.message}`)
      } else {
        response.destroy(err)
      }
    } finally {
      reader.releaseLock()
    }
  })()
}

function toolText(result: unknown): string {
  if (result == null) return ""
  if (typeof result === "string") return result
  const rec = result as { content?: Array<{ type?: string; text?: string }> }
  if (Array.isArray(rec.content)) {
    return rec.content.map((part) => part.text || "").join("")
  }
  try {
    return JSON.stringify(result)
  } catch {
    return String(result)
  }
}

function mapPiEvents(agent: Agent, userText: string, signal?: AbortSignal) {
  return createUIMessageStream({
    execute: async ({ writer }) => {
      const messageId = crypto.randomUUID()
      writer.write({ type: "start", messageId })
      writer.write({ type: "start-step" })

      let textId: string | null = null
      const endText = () => {
        if (!textId) return
        writer.write({ type: "text-end", id: textId })
        textId = null
      }

      const unsub = agent.subscribe((event) => {
        if (event.type === "message_update" && event.assistantMessageEvent?.type === "text_delta") {
          if (!textId) {
            textId = crypto.randomUUID()
            writer.write({ type: "text-start", id: textId })
          }
          writer.write({
            type: "text-delta",
            id: textId,
            delta: event.assistantMessageEvent.delta,
          })
        }

        if (event.type === "tool_execution_start") {
          endText()
          writer.write({
            type: "tool-input-start",
            toolCallId: event.toolCallId,
            toolName: event.toolName,
          })
          writer.write({
            type: "tool-input-available",
            toolCallId: event.toolCallId,
            toolName: event.toolName,
            input: event.args ?? {},
          })
        }

        if (event.type === "tool_execution_end") {
          writer.write({
            type: "tool-output-available",
            toolCallId: event.toolCallId,
            output: toolText(event.result),
          })
        }
      })

      const onAbort = () => {
        try {
          agent.abort()
        } catch {
          /* ignore */
        }
      }
      signal?.addEventListener("abort", onAbort)

      try {
        await agent.prompt(userText)
        endText()
        writer.write({ type: "finish-step" })
        writer.write({ type: "finish" })
      } catch (err) {
        endText()
        const message = err instanceof Error ? err.message : String(err)
        writer.write({ type: "error", errorText: message })
        writer.write({ type: "finish" })
      } finally {
        signal?.removeEventListener("abort", onAbort)
        unsub()
      }
    },
  })
}

/** Map Pi Agent events → AI SDK 5 UIMessage stream for useChat. */
export function piToUIMessageResponse(
  agent: Agent,
  userText: string,
  signal?: AbortSignal,
  outgoing?: ServerResponse,
  extraHeaders?: Headers,
): Response {
  const stream = mapPiEvents(agent, userText, signal)
  const headers = streamHeaders(extraHeaders)
  const body = textFirstSseStream(stream)

  // Node HTTP: wait to send headers until the first body write, so fetch() does
  // not resolve into an empty Stop state before assistant text is available.
  if (outgoing && typeof outgoing.writeHead === "function") {
    pipeTextFirstSseToNode(outgoing, body, headers)
    headers.set(ALREADY_SENT, "1")
    return new Response(null, {
      headers,
    })
  }

  return new Response(body, {
    headers,
  })
}
