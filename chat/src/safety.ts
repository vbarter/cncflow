/** Read-only bash gate. Write/edit are never registered; this is defense in depth. */

const WRITE_TOOLS = new Set(["write", "edit", "strreplace", "apply_patch", "create_file"])

const DENIED_COMMANDS = [
  "sudo", "su", "doas",
  "curl", "wget", "httpie", "aria2c",
  "ssh", "scp", "sftp", "rsync", "ftp", "telnet", "nc", "ncat", "netcat", "socat",
  "chmod", "chown", "chgrp", "mkfs", "dd",
  "apt", "apt-get", "yum", "dnf", "pip", "npm", "pnpm", "yarn",
  "docker", "kubectl", "systemctl",
  "python", "python3", "node", "perl", "ruby", "php",
]

const WRITE_COMMANDS = [
  "rm", "rmdir", "mv", "cp", "install", "touch", "mkdir", "tee", "truncate",
  "ln", "unlink", "sed", "awk", "perl",
]

const WRITE_RE = /(\s|^)(>|>>|tee\b|dd\b)/
const INPLACE_RE = /\bsed\b[^;\n]*\s-i\b|\bperl\b[^;\n]*\s-i\b/
const PARENT_RE = /(^|[/"'\s])\.\.([/"'\s]|$)/

export type BashVerdict = { ok: true } | { ok: false; reason: string }

export function inspectBash(command: unknown): BashVerdict {
  const cmd = String(command || "")
  if (!cmd.trim()) return { ok: false, reason: "empty command" }
  if (cmd.length > 4000) return { ok: false, reason: "command too long" }
  if (PARENT_RE.test(cmd)) return { ok: false, reason: "path may leave jail (..)" }
  if (WRITE_RE.test(cmd) || INPLACE_RE.test(cmd)) {
    return { ok: false, reason: "bash is read-only; writes and redirects are blocked" }
  }

  const tokens = tokenize(cmd)
  for (const token of tokens) {
    const base = token.replace(/^.*\//, "").toLowerCase()
    if (DENIED_COMMANDS.includes(base)) {
      return { ok: false, reason: `command not allowed: ${base}` }
    }
    if (WRITE_COMMANDS.includes(base) && base !== "sed" && base !== "awk") {
      return { ok: false, reason: `write command blocked: ${base}` }
    }
  }
  return { ok: true }
}

function tokenize(command: string): string[] {
  return command
    .split(/[;&|`$\n(){}]+/)
    .flatMap((part) => part.trim().split(/\s+/))
    .filter(Boolean)
}

export function inspectToolName(name: string): BashVerdict {
  const n = String(name || "").toLowerCase()
  if (WRITE_TOOLS.has(n) || n.startsWith("write") || n === "edit") {
    return { ok: false, reason: `${name} is not allowed on the public chat widget` }
  }
  return { ok: true }
}

export const REGISTERED_TOOL_NAMES = ["read", "bash", "ls", "grep"] as const
export const FORBIDDEN_TOOL_NAMES = ["write", "edit"] as const
