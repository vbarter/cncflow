import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { FeatureReview, ViewerToolbar, isReviewTreeFeature } from "../src/components/FeatureReview"

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
  assert.match(inspector.textContent || "", /hole-8.*孔.*D.*Ø.*H/s)
  assert.deepEqual(
    [...inspector.querySelectorAll("input")].map((input) => input.value),
    ["8", "12"],
  )

  fireEvent.click(screen.getByRole("button", { name: /face-local/ }))
  assert.match(inspector.textContent || "", /face-local.*面.*L.*W/s)
  assert.deepEqual(
    [...inspector.querySelectorAll("input")].map((input) => input.value),
    ["18", "9"],
  )
  assert.doesNotMatch(inspector.textContent || "", /hole-8/)
})

test("特征树主标题用中文类型，隐藏 pocket_or_step 残留", () => {
  render(
    <FeatureReview
      partId="part-labels"
      features={[
        {
          feature_id: "slot-0",
          type: "pocket",
          pocket_type: "封闭",
          length: 24,
          width: 12,
          depth: 6,
        },
        {
          feature_id: "surface-0",
          type: "surface",
          surface_type: "自由曲面",
          curvature_radius: 20,
        },
        {
          feature_id: "prismatic-region-0",
          type: "pocket_or_step",
          subtype: "planar_region",
        },
      ].filter(isReviewTreeFeature)}
      processSequence={[]}
      meshAvailable={false}
      locked={false}
      busy={false}
      onToggle={() => {}}
      onPatchFeature={async () => {}}
      onPatchProcess={async () => {}}
    />,
  )
  const tree = screen.getByText("特征树").closest("section")
  assert.ok(tree)
  assert.match(tree.textContent || "", /型腔 · 封闭/)
  assert.match(tree.textContent || "", /曲面 · 自由曲面/)
  assert.match(tree.textContent || "", /slot-0/)
  assert.match(tree.textContent || "", /surface-0/)
  assert.doesNotMatch(tree.textContent || "", /pocket_or_step/)
  assert.doesNotMatch(tree.textContent || "", /prismatic-region/)
  assert.equal(isReviewTreeFeature({
    feature_id: "prismatic-region-0",
    type: "pocket_or_step",
    subtype: "planar_region",
  }), false)
})
