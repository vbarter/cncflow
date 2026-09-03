import fs from "node:fs"
import path from "node:path"
import { jailRoot } from "./config.js"

const JAIL_TREES = [
  "docs/knowledge-base",
  "backend/cncflow_core",
  "frontend/src",
] as const

export { JAIL_TREES }

export function resolveJailPath(jail: string, raw: string): string {
  const input = String(raw || "").trim()
  if (!input) throw new Error("path is required")
  if (input.includes("\0")) throw new Error("invalid path")
  const jailAbs = path.resolve(jail)
  const stripped = input.replace(/^\/+/, "")
  const candidate = path.isAbsolute(input)
    ? path.resolve(input)
    : path.resolve(jailAbs, stripped)
  const rel = path.relative(jailAbs, candidate)
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error("path escapes chat jail")
  }
  return candidate
}

export function assertInsideJail(jail: string, target: string): string {
  return resolveJailPath(jail, path.relative(path.resolve(jail), path.resolve(target)) || ".")
}

export function prepareJail(dest?: string, repoRoot?: string): string {
  const jail = path.resolve(dest || jailRoot())
  const root = path.resolve(repoRoot || path.join(jail, ".."))
  fs.mkdirSync(jail, { recursive: true })
  for (const tree of JAIL_TREES) {
    const src = path.join(root, tree)
    const out = path.join(jail, tree)
    if (!fs.existsSync(src)) continue
    fs.mkdirSync(path.dirname(out), { recursive: true })
    fs.rmSync(out, { recursive: true, force: true })
    copyTree(src, out)
  }
  return jail
}

function copyTree(src: string, dest: string): void {
  const stat = fs.statSync(src)
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true })
    for (const name of fs.readdirSync(src)) {
      if (name === "__pycache__" || name === "node_modules" || name.endsWith(".pyc")) continue
      copyTree(path.join(src, name), path.join(dest, name))
    }
    return
  }
  fs.copyFileSync(src, dest)
}
