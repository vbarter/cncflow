import type { HttpBindings } from "@hono/node-server"
import { serve } from "@hono/node-server"
import { Hono } from "hono"
import { cors } from "hono/cors"
import { createChatAgent, historyMessages, lastUserText } from "./agent.js"
import { piToUIMessageResponse } from "./bridge.js"
import { CHAT_HOST, CHAT_PORT, TUZI_MODEL, jailRoot, tuziApiKey } from "./config.js"
import { FORBIDDEN_TOOL_NAMES, REGISTERED_TOOL_NAMES } from "./safety.js"

const allowed = (process.env.CNCFLOW_CORS_ORIGINS || "*")
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean)

type ChatEnv = { Bindings: HttpBindings }

export function createChatApp(opts?: { createAgent?: typeof createChatAgent }) {
  const makeAgent = opts?.createAgent ?? createChatAgent
  const app = new Hono<ChatEnv>()

  app.use(
    "*",
    cors({
      origin: (origin) => {
        if (!origin) return allowed.includes("*") ? "*" : ""
        if (allowed.includes("*") || allowed.includes(origin)) return origin
        return ""
      },
      allowMethods: ["GET", "POST", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization"],
      maxAge: 86400,
    }),
  )

  app.get("/health", (c) => c.json({
    service: "cncflow-chat",
    model: TUZI_MODEL,
    tools: [...REGISTERED_TOOL_NAMES],
    forbidden: [...FORBIDDEN_TOOL_NAMES],
    key: Boolean(tuziApiKey()),
  }))

  async function handleChat(c: { req: { json: () => Promise<unknown>; raw: Request }; env: HttpBindings }) {
    if (!tuziApiKey()) {
      return new Response(JSON.stringify({ error: "未配置 TUZI_API_KEY" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      })
    }

    const body = (await c.req.json()) as { messages?: unknown }
    const messages = Array.isArray(body.messages) ? body.messages : []
    const userText = lastUserText(messages)
    if (!userText) {
      return new Response(JSON.stringify({ error: "messages 须含用户文本" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })
    }

    const agent = makeAgent(jailRoot())
    const prior = historyMessages(messages)
    if (prior.length) agent.state.messages = prior

    return piToUIMessageResponse(agent, userText, c.req.raw.signal, c.env?.outgoing)
  }

  app.post("/api/v1/chat", (c) => handleChat(c))
  app.post("/api/chat", (c) => handleChat(c))
  return app
}

export const app = createChatApp()

if (process.env.CHAT_NO_LISTEN !== "1") {
  serve({ fetch: app.fetch, hostname: CHAT_HOST, port: CHAT_PORT }, (info) => {
    console.log(`cncflow-chat listening on ${info.address}:${info.port} model=${TUZI_MODEL}`)
  })
}
