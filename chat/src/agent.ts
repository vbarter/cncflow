import { Agent, type AgentMessage } from "@earendil-works/pi-agent-core"
import {
  createModels,
  createProvider,
  envApiKeyAuth,
  type Model,
} from "@earendil-works/pi-ai"
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy"
import { TUZI_BASE_URL, TUZI_MODEL, tuziApiKey } from "./config.js"
import { SYSTEM_PROMPT } from "./prompt.js"
import { inspectBash, inspectToolName } from "./safety.js"
import { forceTuziStream, forceTuziStreamFetch } from "./stream.js"
import { createReadOnlyTools } from "./tools.js"

export function createTuziModel(): { models: ReturnType<typeof createModels>; model: Model<"openai-completions"> } {
  const model = {
    id: TUZI_MODEL,
    name: TUZI_MODEL,
    api: "openai-completions",
    provider: "tuzi",
    baseUrl: TUZI_BASE_URL,
    reasoning: false,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128000,
    maxTokens: 8192,
    compat: {
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      supportsStore: false,
      maxTokensField: "max_tokens" as const,
    },
  } satisfies Model<"openai-completions">

  const tuzi = createProvider({
    id: "tuzi",
    name: "tu-zi",
    baseUrl: TUZI_BASE_URL,
    auth: { apiKey: envApiKeyAuth("tu-zi", ["TUZI_API_KEY", "VISION_API_KEY"]) },
    models: [model],
    api: openAICompletionsApi(),
  })

  const models = createModels()
  models.setProvider(tuzi)
  const resolved = models.getModel("tuzi", TUZI_MODEL)
  if (!resolved || resolved.api !== "openai-completions") {
    throw new Error(`tu-zi model not registered: ${TUZI_MODEL}`)
  }
  return { models, model: resolved as Model<"openai-completions"> }
}

export function createChatAgent(jail: string): Agent {
  const { models, model } = createTuziModel()
  const tools = createReadOnlyTools(jail)

  return new Agent({
    initialState: {
      systemPrompt: SYSTEM_PROMPT,
      model,
      thinkingLevel: "off",
      tools,
      messages: [],
    },
    streamFn: (model, context, options) =>
      models.streamSimple(model, context, {
        ...options,
        fetch: forceTuziStreamFetch(options?.fetch),
        onPayload: (payload) => forceTuziStream(payload),
      }),
    getApiKey: async () => tuziApiKey() || undefined,
    beforeToolCall: async ({ toolCall, args }) => {
      const nameGate = inspectToolName(toolCall.name)
      if (!nameGate.ok) return { block: true, reason: nameGate.reason }
      if (toolCall.name === "bash") {
        const command = (args as { command?: string }).command
        const bashGate = inspectBash(command)
        if (!bashGate.ok) return { block: true, reason: bashGate.reason }
      }
      return undefined
    },
  })
}

type UiPart = { type?: string; text?: string }
type UiMessage = { role?: string; parts?: UiPart[]; content?: string }

export function lastUserText(messages: unknown[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i] as UiMessage
    if (msg.role !== "user") continue
    const text = uiText(msg)
    if (text) return text
  }
  return ""
}

export function historyMessages(messages: unknown[]): AgentMessage[] {
  const prior = messages.slice(0, -1) as UiMessage[]
  const out: AgentMessage[] = []
  for (const msg of prior) {
    const text = uiText(msg)
    if (!text) continue
    if (msg.role === "user") {
      out.push({ role: "user", content: text, timestamp: Date.now() })
    } else if (msg.role === "assistant") {
      out.push({
        role: "assistant",
        content: [{ type: "text", text }],
        timestamp: Date.now(),
        stopReason: "stop",
        api: "openai-completions",
        provider: "tuzi",
        model: TUZI_MODEL,
        usage: {
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
          totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
      } as AgentMessage)
    }
  }
  return out
}

function uiText(msg: UiMessage): string {
  if (typeof msg.content === "string" && msg.content.trim()) return msg.content
  return (msg.parts || [])
    .filter((part) => part.type === "text" && part.text)
    .map((part) => part.text)
    .join("")
    .trim()
}

export function registeredToolNames(agent: Agent): string[] {
  return agent.state.tools.map((tool) => tool.name)
}
