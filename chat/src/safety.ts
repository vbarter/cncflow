/** Only commands with no file/network mutation surface are allowed. */
const READ_ONLY_COMMANDS = new Set([
  "cat",
  "file",
  "find",
  "grep",
  "head",
  "ls",
  "pwd",
  "rg",
  "stat",
  "tail",
  "wc",
])

const ALLOWED_TOOLS = new Set(["read", "bash"])
const PARENT_RE = /(^|[/"'\s])\.\.([/"'\s]|$)/
const ABSOLUTE_PATH_RE = /(^|[\s=])["']?\//
const SHELL_ESCAPE_RE = /[;<>&`$\\\n\r()[\]{}]/
const FIND_MUTATION_RE = /(^|\s)-(delete|exec|execdir|ok|okdir|fprint|fprint0|fls)(\s|$)/
const RG_EXEC_RE = /(^|\s)--pre(?:-glob)?(?:[=\s]|$)/
const GREP_FILE_RE = /(^|\s)(?:-f|--file|--exclude-from|--include-from)(?:[=\s]|$)/

export type BashVerdict = { ok: true } | { ok: false; reason: string }

export function inspectBash(command: unknown): BashVerdict {
  const cmd = String(command || "")
  if (!cmd.trim()) return { ok: false, reason: "empty command" }
  if (cmd.length > 4000) return { ok: false, reason: "command too long" }
  if (PARENT_RE.test(cmd)) return { ok: false, reason: "path may leave jail (..)" }
  if (ABSOLUTE_PATH_RE.test(cmd) || /(^|\s)~[/\s]/.test(cmd)) {
    return { ok: false, reason: "absolute and home paths are outside the jail" }
  }
  if (SHELL_ESCAPE_RE.test(cmd)) {
    return { ok: false, reason: "shell control, substitution, and redirection are blocked" }
  }
  if (FIND_MUTATION_RE.test(cmd)) {
    return { ok: false, reason: "mutating find actions are blocked" }
  }
  if (RG_EXEC_RE.test(cmd) || GREP_FILE_RE.test(cmd)) {
    return { ok: false, reason: "options that execute commands or read outside operands are blocked" }
  }

  for (const segment of cmd.split("|")) {
    const executable = segment.trim().match(/^([a-zA-Z0-9_-]+)/)?.[1]?.toLowerCase()
    if (!executable || !READ_ONLY_COMMANDS.has(executable)) {
      return { ok: false, reason: `only read-only commands are allowed: ${executable || "unknown"}` }
    }
  }
  return { ok: true }
}

export function inspectToolName(name: string): BashVerdict {
  const n = String(name || "").toLowerCase()
  if (!ALLOWED_TOOLS.has(n)) {
    return { ok: false, reason: `only read and bash are allowed; ${name} is disabled` }
  }
  return { ok: true }
}

export const REGISTERED_TOOL_NAMES = ["read", "bash"] as const
export const FORBIDDEN_TOOL_NAMES = ["write", "edit", "ls", "grep"] as const
