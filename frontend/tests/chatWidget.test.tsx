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

const { cleanup, fireEvent, render, screen } = await import("@testing-library/react")

afterEach(cleanup)

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
