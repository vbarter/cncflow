import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { CHAT_API, chatTransportApi } from "../src/chatApi"
import { ChatWidget } from "../src/components/ChatWidget"

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
})
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
  MutationObserver: dom.window.MutationObserver,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: dom.window.navigator,
})

const { act, cleanup, fireEvent, render, screen } = await import("@testing-library/react")
const nativeFetch = globalThis.fetch

afterEach(() => {
  cleanup()
  globalThis.fetch = nativeFetch
})

const frame = (part: unknown) => `data: ${JSON.stringify(part)}\n\n`

test("FAB 叠在页面上，useChat 打到 /api/v1/chat", () => {
  assert.match(CHAT_API, /\/api\/v1\/chat$/)
  assert.equal(chatTransportApi(), CHAT_API)

  const { container } = render(
    <main>
      <div data-testid="quote-page" className="mx-auto max-w-[1440px] px-4 py-5">报价页</div>
      <ChatWidget />
    </main>,
  )

  const fab = screen.getByTestId("chat-fab")
  assert.ok(fab)
  assert.match(fab.className, /\bfixed\b/)
  assert.match(fab.className, /\bbottom-/)
  assert.match(fab.className, /\bright-/)

  const page = screen.getByTestId("quote-page")
  assert.equal(page.textContent, "报价页")
  assert.doesNotMatch(page.className, /\bpr-16\b/)
  assert.doesNotMatch(page.className, /\bpb-16\b/)
  assert.equal(container.querySelector("[data-testid=quote-page]")?.nextElementSibling, fab)

  fireEvent.click(fab)
  assert.ok(screen.getByText("可以问手册规则或这份代码怎么报价"))
})

test("同 burst 一次呈现，只有后续网络 payload 才让 Stop 下文本增长", async () => {
  const encoder = new TextEncoder()
  let networkPayloads = 0
  let streamController!: ReadableStreamDefaultController<Uint8Array>
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      streamController = controller
    },
  }), {
    headers: {
      "Content-Type": "text/event-stream",
      "x-vercel-ai-ui-message-stream": "v1",
    },
  })

  const { container } = render(<ChatWidget />)
  fireEvent.click(screen.getByTestId("chat-fab"))
  fireEvent.change(screen.getByPlaceholderText("可以问手册规则或这份代码怎么报价"), {
    target: { value: "孔工艺链" },
  })
  fireEvent.click(screen.getByText("发送"))

  const assistantText = () => {
    const nodes = container.querySelectorAll(".whitespace-pre-wrap")
    return nodes.length > 1 ? nodes.item(nodes.length - 1)?.textContent || "" : ""
  }
  const snapshots: Array<{ payload: number; text: string; stop: boolean }> = []
  const observer = new MutationObserver(() => {
    const text = assistantText()
    if (!text || snapshots.at(-1)?.text === text) return
    snapshots.push({
      payload: networkPayloads,
      text,
      stop: Boolean(screen.queryByLabelText("停止生成")),
    })
  })
  observer.observe(container, { childList: true, characterData: true, subtree: true })

  assert.ok(screen.getByLabelText("停止生成"))
  assert.match(
    screen.getByRole("dialog").getAttribute("data-chat-status") || "",
    /submitted|streaming/,
  )

  networkPayloads++
  streamController.enqueue(encoder.encode([
    frame({ type: "start", messageId: "assistant-1" }),
    frame({ type: "start-step" }),
    frame({ type: "text-start", id: "text-1" }),
    frame({ type: "text-delta", id: "text-1", delta: "孔" }),
    frame({ type: "text-delta", id: "text-1", delta: "工艺" }),
  ].join("")))
  for (let i = 0; i < 100 && assistantText() !== "孔工艺"; i++) {
    await act(() => new Promise((resolve) => setTimeout(resolve, 2)))
  }
  // Catch #141's 16ms paint yield: it exposes "孔" before "孔工艺".
  await act(() => new Promise((resolve) => setTimeout(resolve, 40)))

  assert.equal(assistantText(), "孔工艺")
  assert.ok(screen.getByLabelText("停止生成"))
  assert.deepEqual(
    snapshots.filter(({ payload }) => payload === 1).map(({ text }) => text),
    ["孔工艺"],
    `one network payload dripped across renders: ${JSON.stringify(snapshots)}`,
  )
  assert.equal(snapshots[0]?.stop, true)

  networkPayloads++
  streamController.enqueue(encoder.encode(
    frame({ type: "text-delta", id: "text-1", delta: "链" }),
  ))
  for (let i = 0; i < 200 && assistantText() !== "孔工艺链"; i++) {
    await act(() => new Promise((resolve) => setTimeout(resolve, 2)))
  }
  assert.equal(assistantText(), "孔工艺链")
  assert.ok(screen.getByLabelText("停止生成"))
  assert.equal(snapshots.at(-1)?.payload, 2)
  assert.equal(snapshots.at(-1)?.stop, true)

  networkPayloads++
  streamController.enqueue(encoder.encode([
    frame({ type: "text-delta", id: "text-1", delta: "文".repeat(343) }),
    frame({ type: "text-end", id: "text-1" }),
    frame({ type: "finish-step" }),
    frame({ type: "finish" }),
    "data: [DONE]\n\n",
  ].join("")))
  streamController.close()
  for (let i = 0; i < 200 && assistantText().length !== 347; i++) {
    await act(() => new Promise((resolve) => setTimeout(resolve, 2)))
  }
  assert.equal(assistantText().length, 347)
  assert.equal(snapshots.at(-1)?.payload, 3)

  for (let i = 0; i < 200 && screen.queryByLabelText("停止生成"); i++) {
    await act(() => new Promise((resolve) => setTimeout(resolve, 2)))
  }
  assert.equal(screen.queryByLabelText("停止生成"), null)
  assert.equal(screen.getByRole("dialog").getAttribute("data-chat-status"), "ready")
  observer.disconnect()
})
