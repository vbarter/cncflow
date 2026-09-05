import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { ViewerToolbar } from "../src/components/FeatureReview"

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

test("审查视口工具条保留适应/前/顶/侧/ISO/剖切，默认 ISO 高亮", () => {
  const views = []
  render(
    <ViewerToolbar
      view="iso"
      section={false}
      sectionT={0.5}
      onView={(v) => views.push(v)}
      onSection={() => {}}
      onSectionT={() => {}}
    />,
  )

  assert.ok(screen.getByRole("button", { name: "适应窗口" }))
  assert.ok(screen.getByRole("button", { name: "前视图" }))
  assert.ok(screen.getByRole("button", { name: "顶视图" }))
  assert.ok(screen.getByRole("button", { name: "侧视图" }))
  const iso = screen.getByRole("button", { name: "等轴视图" })
  assert.match(iso.className, /bg-blue-600/)
  assert.equal(iso.textContent, "ISO")
  assert.ok(screen.getByRole("button", { name: "剖切" }))

  fireEvent.click(screen.getByRole("button", { name: "前视图" }))
  fireEvent.click(screen.getByRole("button", { name: "适应窗口" }))
  assert.deepEqual(views, ["front", "fit"])
})
