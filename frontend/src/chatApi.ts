import { DefaultChatTransport } from "ai"
import { API } from "./api"

/** Worker-proxied chat. Matches existing `/api/v1` prefix. */
export const CHAT_API = `${API}/chat`

export function createChatTransport() {
  return new DefaultChatTransport({ api: CHAT_API })
}

export function chatTransportApi(transport = createChatTransport()): string {
  return (transport as unknown as { api: string }).api
}
