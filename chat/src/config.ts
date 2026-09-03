import path from "node:path"
import { fileURLToPath } from "node:url"

const here = path.dirname(fileURLToPath(import.meta.url))

/** Repo root when running from chat/src or chat/dist. */
export const REPO_ROOT = path.resolve(here, "../..")

export const TUZI_BASE_URL = process.env.TUZI_BASE_URL || "https://api.tu-zi.com/v1"
export const TUZI_MODEL = process.env.TUZI_MODEL || process.env.VISION_MODEL || "gpt-4.1-mini"
export const CHAT_PORT = Number(process.env.CHAT_PORT || 3002)
export const CHAT_HOST = process.env.CHAT_HOST || "0.0.0.0"
export const BASH_TIMEOUT_MS = Number(process.env.CHAT_BASH_TIMEOUT_MS || 12_000)
export const MAX_TOOL_OUTPUT = Number(process.env.CHAT_MAX_TOOL_OUTPUT || 48_000)
export const MAX_READ_BYTES = Number(process.env.CHAT_MAX_READ_BYTES || 120_000)

export function tuziApiKey(): string {
  return process.env.TUZI_API_KEY || process.env.VISION_API_KEY || ""
}

/** Jail cwd. Container sets CHAT_JAIL=/app/chat-jail; local tests pass an explicit dir. */
export function jailRoot(override?: string): string {
  const raw = override || process.env.CHAT_JAIL || path.join(REPO_ROOT, "chat-jail")
  return path.resolve(raw)
}
