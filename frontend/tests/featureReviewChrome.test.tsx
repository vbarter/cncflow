import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import {
  FeatureReview,
  ViewerToolbar,
  featureTreeTitle,
  isReviewTreeFeature,
} from "../src/components/FeatureReview"

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

test("特征树标题以中文类型和关键尺寸为主", () => {
  assert.equal(featureTreeTitle({
    type: "hole",
    diameter_mm: 8,
    depth_mm: 12,
    hole_type: "through",
  }), "孔 · Ø8×H12 通孔")
  assert.equal(featureTreeTitle({
    type: "face",
    length: 80,
    width: 60,
    face_position: "水平",
  }), "面 · L80×W60 水平")
  assert.equal(featureTreeTitle({
    type: "pocket",
    pocket_type: "开放",
    length: 24,
    width: 12,
    depth: 6,
  }), "型腔 · 开放 L24×W12×H6")
  assert.equal(featureTreeTitle({
    type: "slot",
    pocket_type: "开放",
    dimensions: { length: 24, width: 8, depth: 4 },
  }), "槽 · 开放 L24×W8×H4")
  assert.equal(featureTreeTitle({
    type: "thread",
    nominal_d: 8,
    pitch: 1.25,
    thread_length: 12,
  }), "螺纹 · M8×P1.25×H12")
  assert.equal(featureTreeTitle({
    type: "surface",
    surface_type: "自由曲面",
    curvature_radius: 20,
  }), "曲面 · 自由曲面 R20")
  assert.equal(featureTreeTitle({
    type: "step",
    length: 30,
    width: 18,
    height: 5,
  }), "台阶 · L30×W18×H5")
  assert.equal(featureTreeTitle({
    type: "outer_cylinder",
    diameter_mm: 50,
    depth_mm: 24,
  }), "外圆 · Ø50×H24")
  assert.equal(featureTreeTitle({
    type: "outer_cylinder",
    dimensions: { diameter_mm: 32, length: 18 },
  }), "外圆 · Ø32×H18")
  assert.equal(featureTreeTitle({
    type: "chamfer",
    chamfer_mm: 0.8,
  }), "倒角 · C0.8")
  assert.equal(featureTreeTitle({
    type: "fillet",
    dimensions: { fillet_radius: 2 },
  }), "圆角 · R2")
  assert.equal(featureTreeTitle({
    type: "chamfer",
    dimensions: { x: 1, y: 20, z: 20 },
  }), "倒角")
  assert.equal(featureTreeTitle({
    type: "fillet",
  }), "圆角")
})

test("特征树显示报价特征和仅供审查的外圆、倒角、圆角", () => {
  const allowed = ["hole", "outer_cylinder", "chamfer", "fillet", "face", "pocket", "slot", "thread", "surface", "step"]
  assert.deepEqual(
    allowed.filter((type) => isReviewTreeFeature({ type, feature_id: `${type}-0` })),
    allowed,
  )
  for (const type of ["pocket_or_step", "boss", ""]) {
    assert.equal(isReviewTreeFeature({ type, feature_id: `${type || "unknown"}-0` }), false)
  }

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
        {
          feature_id: "od-0",
          type: "outer_cylinder",
          diameter_mm: 50,
          depth_mm: 24,
          process_chain: [
            { step_id: "od-0:rough", order: 1, process: "rough_turn_outer_cylinder", name: "粗车外圆" },
            { step_id: "od-0:finish", order: 2, process: "finish_turn_outer_cylinder", name: "精车外圆" },
          ],
          gaps: ["缺少车削 Vc/f/ap 参数表", "缺少径向余量表"],
        },
        {
          feature_id: "chamfer-0",
          type: "chamfer",
          C: 0.8,
          quote_status: "待手册公式",
          quote_excluded: true,
          process_chain: [
            { step_id: "chamfer-0:review", order: 1, process: "review_independent_chamfer", name: "独立倒角加工", status: "待手册公式" },
          ],
          gaps: ["独立特征 schema 与 C/R 格式未冻结"],
          warnings: ["可能是沉头孔、倒角或锥面，需人工分类"],
        },
        {
          feature_id: "fillet-0",
          type: "fillet",
          R: 2,
          quote_status: "待手册公式",
          quote_excluded: true,
          process_chain: [
            { step_id: "fillet-0:review", order: 1, process: "review_independent_fillet", name: "独立圆角加工", status: "待手册公式" },
          ],
          gaps: ["缺少独立圆角刀具 SKU 匹配表"],
        },
        { feature_id: "boss-0", type: "boss" },
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
  const tree = screen.getByText("特征树").closest("section")
  assert.ok(tree)
  assert.match(tree.textContent || "", /型腔 · 封闭 L24×W12×H6/)
  assert.match(tree.textContent || "", /曲面 · 自由曲面 R20/)
  assert.match(tree.textContent || "", /slot-0/)
  assert.match(tree.textContent || "", /surface-0/)
  assert.match(tree.textContent || "", /外圆 · Ø50×H24/)
  assert.match(tree.textContent || "", /od-0/)
  assert.match(tree.textContent || "", /倒角 · C0.8/)
  assert.match(tree.textContent || "", /chamfer-0/)
  assert.match(tree.textContent || "", /圆角 · R2/)
  assert.match(tree.textContent || "", /fillet-0/)
  assert.doesNotMatch(tree.textContent || "", /pocket_or_step/)
  assert.doesNotMatch(tree.textContent || "", /prismatic-region/)
  assert.doesNotMatch(tree.textContent || "", /outer_cylinder|boss/)

  fireEvent.click(screen.getByRole("button", { name: /od-0/ }))
  const inspector = screen.getByText("特征详细参数").closest("section")
  assert.ok(inspector)
  assert.match(inspector.textContent || "", /粗车外圆.*待手册公式.*精车外圆.*待手册公式/s)
  assert.match(inspector.textContent || "", /缺少车削 Vc\/f\/ap 参数表/)
  assert.match(inspector.textContent || "", /缺少径向余量表/)
  assert.match(inspector.textContent || "", /不计入报价/)
  assert.doesNotMatch(inspector.textContent || "", /暂无匹配工序/)

  fireEvent.click(screen.getByRole("button", { name: /chamfer-0/ }))
  assert.match(inspector.textContent || "", /倒角/)
  assert.match(inspector.textContent || "", /0.8 mm/)
  assert.match(inspector.textContent || "", /独立倒角加工.*待手册公式/s)
  assert.match(inspector.textContent || "", /独立特征 schema 与 C\/R 格式未冻结/)
  assert.match(inspector.textContent || "", /可能是沉头孔、倒角或锥面，需人工分类/)
  assert.match(inspector.textContent || "", /待手册公式 · 不计入报价/)
})
