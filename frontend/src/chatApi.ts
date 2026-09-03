import {
  DefaultChatTransport,
  type ChatTransport,
  type UIMessage,
  type UIMessageChunk,
} from "ai"
import { API } from "./api"

/** Worker-proxied chat. Matches existing `/api/v1` prefix. */
export const CHAT_API = `${API}/chat`

type SendOptions = Parameters<ChatTransport<UIMessage>["sendMessages"]>[0]
type ReconnectOptions = Parameters<ChatTransport<UIMessage>["reconnectToStream"]>[0]

/**
 * Do not drain multiple real provider deltas between two browser paints.
 * Cloudflare can deliver several SSE events in one network burst; yielding here
 * preserves their real boundaries in the DOM without slicing or replaying text.
 */
function afterNextPaint(): Promise<void> {
  if (typeof requestAnimationFrame !== "function") {
    return new Promise((resolve) => setTimeout(resolve, 16))
  }
  return new Promise((resolve) => {
    let settled = false
    let frame = 0
    let timeout = 0
    const finish = () => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      cancelAnimationFrame(frame)
      resolve()
    }
    timeout = setTimeout(finish, 50)
    frame = requestAnimationFrame(() => setTimeout(finish, 0))
  })
}

export function paintAwareUIStream(
  stream: ReadableStream<UIMessageChunk>,
): ReadableStream<UIMessageChunk> {
  return stream.pipeThrough(new TransformStream({
    async transform(chunk, controller) {
      controller.enqueue(chunk)
      if (chunk.type === "text-delta") await afterNextPaint()
    },
  }))
}

export function createChatTransport() {
  const upstream = new DefaultChatTransport({ api: CHAT_API })
  return {
    api: CHAT_API,
    async sendMessages(options: SendOptions) {
      return paintAwareUIStream(await upstream.sendMessages(options))
    },
    async reconnectToStream(options: ReconnectOptions) {
      const stream = await upstream.reconnectToStream(options)
      return stream ? paintAwareUIStream(stream) : null
    },
  } satisfies ChatTransport<UIMessage> & { api: string }
}

export function chatTransportApi(transport = createChatTransport()): string {
  return transport.api
}
