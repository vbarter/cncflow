import { spawn } from "node:child_process"
import fs from "node:fs"
import type { AgentTool } from "@earendil-works/pi-agent-core"
import { Type } from "@earendil-works/pi-ai"
import { BASH_TIMEOUT_MS, MAX_READ_BYTES, MAX_TOOL_OUTPUT } from "./config.js"
import { resolveJailPath } from "./jail.js"
import { FORBIDDEN_TOOL_NAMES, REGISTERED_TOOL_NAMES, inspectBash } from "./safety.js"

export { FORBIDDEN_TOOL_NAMES, REGISTERED_TOOL_NAMES }

function clip(text: string, max = MAX_TOOL_OUTPUT): string {
  if (text.length <= max) return text
  return `${text.slice(0, max)}\n…[truncated ${text.length - max} bytes]`
}

function textResult(text: string, details: Record<string, unknown> = {}) {
  return { content: [{ type: "text" as const, text: clip(text) }], details }
}

const ReadParams = Type.Object({
  path: Type.String({ description: "Path relative to the chat jail" }),
})

const BashParams = Type.Object({
  command: Type.String({ description: "Read-only shell command; cwd is the jail" }),
})

export function createReadOnlyTools(jail: string): AgentTool[] {
  const read: AgentTool<typeof ReadParams> = {
    name: "read",
    label: "read",
    description: "Read a text file inside the chat jail (handbook, rules YAML, or project code).",
    parameters: ReadParams,
    execute: async (_id, params) => {
      const target = resolveJailPath(jail, params.path)
      const stat = fs.statSync(target)
      if (!stat.isFile()) throw new Error("not a file")
      if (stat.size > MAX_READ_BYTES) {
        const fd = fs.openSync(target, "r")
        const buf = Buffer.alloc(MAX_READ_BYTES)
        const n = fs.readSync(fd, buf, 0, MAX_READ_BYTES, 0)
        fs.closeSync(fd)
        return textResult(`${buf.slice(0, n).toString("utf8")}\n…[truncated]`, { path: params.path })
      }
      return textResult(fs.readFileSync(target, "utf8"), { path: params.path })
    },
  }

  const bash: AgentTool<typeof BashParams> = {
    name: "bash",
    label: "bash",
    description: "Read-only bash in the jail. Only safe inspection commands are allowed; no writes, network, or path escape.",
    parameters: BashParams,
    execute: async (_id, params, signal) => {
      const verdict = inspectBash(params.command)
      if (!verdict.ok) throw new Error(verdict.reason)
      const output = await runJailed(jail, params.command, signal)
      return textResult(output, { command: params.command })
    },
  }

  return [read, bash]
}

function runJailed(jail: string, command: string, signal?: AbortSignal): Promise<string> {
  return runBinary(jail, "/bin/bash", ["-r", "-c", command], signal)
}

function runBinary(
  jail: string,
  bin: string,
  args: string[],
  signal?: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(bin, args, {
      cwd: jail,
      env: {
        PATH: "/usr/bin:/bin",
        HOME: jail,
        LANG: "C.UTF-8",
      },
      stdio: ["ignore", "pipe", "pipe"],
    })
    const chunks: Buffer[] = []
    let size = 0
    const onData = (buf: Buffer) => {
      size += buf.length
      if (size <= MAX_TOOL_OUTPUT) chunks.push(buf)
    }
    child.stdout?.on("data", onData)
    child.stderr?.on("data", onData)

    const timer = setTimeout(() => {
      child.kill("SIGKILL")
      reject(new Error(`timeout after ${BASH_TIMEOUT_MS}ms`))
    }, BASH_TIMEOUT_MS)

    const onAbort = () => child.kill("SIGKILL")
    signal?.addEventListener("abort", onAbort)

    child.on("error", (err) => {
      clearTimeout(timer)
      signal?.removeEventListener("abort", onAbort)
      reject(err)
    })
    child.on("close", (code) => {
      clearTimeout(timer)
      signal?.removeEventListener("abort", onAbort)
      const text = Buffer.concat(chunks).toString("utf8")
      if (code !== 0 && !text) {
        reject(new Error(`${bin} exited ${code}`))
        return
      }
      resolve(clip(text + (size > MAX_TOOL_OUTPUT ? "\n…[truncated]" : "")))
    })
  })
}
