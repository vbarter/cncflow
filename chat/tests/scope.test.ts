import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { CHAT_DOES_NOT_OWN_QUOTE_PINS, SYSTEM_PROMPT } from "../src/prompt.ts"

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")
const handbook = path.join(repo, "docs/knowledge-base/CNC知识库使用手册-v5.1.md")

test("empty process-route and quote pins are not the job of chat", () => {
  assert.match(SYSTEM_PROMPT, /不改报价/)
  assert.match(SYSTEM_PROMPT, /D9-4/)
  assert.match(SYSTEM_PROMPT, /engine\.py/)
  assert.match(SYSTEM_PROMPT, /禁止改数字/)
  for (const pin of ["211.39", "211.59", "211.19", "54.23", "214.18"]) {
    assert.equal(
      SYSTEM_PROMPT.includes(pin),
      false,
      `chat prompt must not restate pin ${pin}`,
    )
  }
  assert.ok(CHAT_DOES_NOT_OWN_QUOTE_PINS.some((line) => line.includes("engine.py")))
  assert.ok(CHAT_DOES_NOT_OWN_QUOTE_PINS.some((line) => line.includes("211.39")))
})

test("handbook covers hole process chain for 业务抽", () => {
  const text = fs.readFileSync(handbook, "utf8")
  assert.match(text, /② 工艺路线（孔工艺链）/)
  assert.match(text, /process_chain\.py/)
  assert.match(text, /hole\/process_chain\.yaml/)
  assert.match(text, /点钻/)
  assert.match(text, /F01–F09/)
  assert.match(text, /D9-4/)
  assert.match(text, /engine\.py/)
})
