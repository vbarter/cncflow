import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { createReadOnlyTools, FORBIDDEN_TOOL_NAMES, REGISTERED_TOOL_NAMES } from "../src/tools.ts"
import { inspectBash, inspectToolName } from "../src/safety.ts"

test("write/edit are not registered; read and bash are", () => {
  assert.ok(REGISTERED_TOOL_NAMES.includes("read"))
  assert.ok(REGISTERED_TOOL_NAMES.includes("bash"))
  assert.ok(!REGISTERED_TOOL_NAMES.includes("write"))
  assert.ok(!REGISTERED_TOOL_NAMES.includes("edit"))
  const tools = createReadOnlyTools(os.tmpdir())
  const names = tools.map((tool) => tool.name)
  assert.deepEqual(names, ["read", "bash"])
  for (const banned of FORBIDDEN_TOOL_NAMES) {
    assert.ok(!names.includes(banned))
    assert.equal(inspectToolName(banned).ok, false)
  }
})

test("bash inspect blocks writes, network, sudo, and ..", () => {
  assert.equal(inspectBash("ls docs/knowledge-base").ok, true)
  assert.equal(inspectBash("grep -n generate_chain backend/cncflow_core/features/hole/process_chain.py").ok, true)
  assert.equal(inspectBash("echo hi > /tmp/x").ok, false)
  assert.equal(inspectBash("rm -rf /").ok, false)
  assert.equal(inspectBash("curl https://example.com").ok, false)
  assert.equal(inspectBash("wget http://x").ok, false)
  assert.equal(inspectBash("sudo ls").ok, false)
  assert.equal(inspectBash("cat ../etc/passwd").ok, false)
  assert.equal(inspectBash("cat /etc/passwd").ok, false)
  assert.equal(inspectBash("python -c 'print(1)'").ok, false)
  assert.equal(inspectBash("find . -delete").ok, false)
  assert.equal(inspectBash("find . -exec cat {} +").ok, false)
  assert.equal(inspectBash("rg --pre sh needle .").ok, false)
  assert.equal(inspectBash("cat docs/knowledge-base/README.md | head").ok, true)
})

test("read stays inside jail", async () => {
  const jail = fs.mkdtempSync(path.join(os.tmpdir(), "cnc-jail-"))
  fs.mkdirSync(path.join(jail, "docs", "knowledge-base"), { recursive: true })
  fs.writeFileSync(path.join(jail, "docs/knowledge-base/note.md"), "孔工艺链\n")
  const [read] = createReadOnlyTools(jail)
  const ok = await read.execute("t1", { path: "docs/knowledge-base/note.md" }, undefined, undefined)
  assert.match(ok.content[0].text, /孔工艺链/)
  await assert.rejects(
    () => read.execute("t2", { path: "../etc/passwd" }, undefined, undefined),
    /jail/,
  )
})

test("bash tool cannot create or mutate files", async () => {
  const jail = fs.mkdtempSync(path.join(os.tmpdir(), "cnc-bash-jail-"))
  fs.writeFileSync(path.join(jail, "handbook.md"), "hole process chain\n")
  const bash = createReadOnlyTools(jail).find((tool) => tool.name === "bash")
  assert.ok(bash)

  const result = await bash.execute(
    "t3",
    { command: "grep -n hole handbook.md | head" },
    undefined,
    undefined,
  )
  assert.match(result.content[0].text, /hole process chain/)
  await assert.rejects(
    () => bash.execute("t4", { command: "touch changed" }, undefined, undefined),
    /read-only commands/,
  )
  assert.equal(fs.existsSync(path.join(jail, "changed")), false)
})
