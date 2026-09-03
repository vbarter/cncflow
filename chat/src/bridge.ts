import type { ServerResponse } from "node:http"
import { createUIMessageStream, createUIMessageStreamResponse, pipeUIMessageStreamToResponse } from "ai"
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
): Response {
  const stream = mapPiEvents(agent, userText, signal)

  // Node HTTP: write SSE chunks as they arrive. Skips @hono/node-server's
  // 2-chunk pre-read that can attach Content-Length and dump the full body.
  if (outgoing && typeof outgoing.writeHead === "function") {
    pipeUIMessageStreamToResponse({
      response: outgoing,
      stream,
      headers: STREAM_HEADERS,
    })
    if (typeof outgoing.flushHeaders === "function") outgoing.flushHeaders()
    return new Response(null, {
      headers: { [ALREADY_SENT]: "1", ...STREAM_HEADERS },
    })
  }

  return createUIMessageStreamResponse({
    stream,
    headers: STREAM_HEADERS,
  })
}
