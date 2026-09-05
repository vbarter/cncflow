import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { FeatureReview, ViewerToolbar } from "../src/components/FeatureReview"

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

test("特征树连续选择 hole/face 时右侧参数跟随同一 feature id", () => {
  render(
    <FeatureReview
      partId="part-pick"
      features={[
        {
          feature_id: "hole-8",
          type: "hole",
          diameter_mm: 8,
          depth_mm: 12,
          location: { x: 0, y: 0, z: 0 },
          axis: { x: 0, y: 0, z: 1 },
        },
        {
          feature_id: "face-local",
          type: "face",
          length: 18,
          width: 9,
          location: { x: 20, y: 0, z: 0 },
          axis: { x: 0, y: 0, z: 1 },
        },
      ]}
      processSequence={[]}
      meshAvailable={false}
      locked={false}
      busy={false}
      onToggle={() => {}}
      onPatchFeature={async () => {}}
      onPatchProcess={async () => {}}
    />,
  )
  const inspector = screen.getByText("特征详细参数").closest("section")
  assert.ok(inspector)

  fireEvent.click(screen.getByRole("button", { name: /hole-8/ }))
  assert.match(inspector.textContent || "", /hole-8.*hole.*Ø.*8.*H.*12/s)

  fireEvent.click(screen.getByRole("button", { name: /face-local/ }))
  assert.match(inspector.textContent || "", /face-local.*face.*L.*18.*W.*9/s)
  assert.doesNotMatch(inspector.textContent || "", /hole-8/)
})
