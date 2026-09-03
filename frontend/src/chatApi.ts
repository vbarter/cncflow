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
 * Let React commit each real provider delta before draining the next queued one.
 * Cloudflare may deliver many SSE events in one network burst; without this yield,
 * useChat applies all snapshots in one task and the browser paints only the last.
 */
function afterNextPaint(): Promise<void> {
  if (typeof requestAnimationFrame !== "function") {
    return new Promise((resolve) => setTimeout(resolve, 16))
  }
  return new Promise((resolve) => {
    requestAnimationFrame(() => setTimeout(resolve, 0))
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
