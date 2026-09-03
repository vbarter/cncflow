import { createUIMessageStream, createUIMessageStreamResponse } from "ai"
import type { Agent } from "@earendil-works/pi-agent-core"

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

/** Map Pi Agent events → AI SDK 5 UIMessage stream for useChat. */
export function piToUIMessageResponse(agent: Agent, userText: string, signal?: AbortSignal): Response {
  const stream = createUIMessageStream({
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

  return createUIMessageStreamResponse({
    stream,
    headers: {
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  })
}
