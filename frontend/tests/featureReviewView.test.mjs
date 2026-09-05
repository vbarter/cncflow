import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import * as THREE from "three"
import {
  ISO_DIRECTION,
  VIEW_FILL,
  applyView,
  contactShadowFromBox,
  fitViewDistance,
  orientedQuat,
  shouldApplyRequestedView,
  viewFillHeight,
} from "../src/components/featureReviewView.ts"

const source = await readFile(
  new URL("../src/components/FeatureReview.tsx", import.meta.url),
  "utf8",
)

function camera(fov = 42, aspect = 16 / 9) {
  const cam = new THREE.PerspectiveCamera(fov, aspect, 0.1, 4000)
  cam.position.set(72, 48, 62)
  return cam
}

function boxFromSize(x, y, z) {
  return new THREE.Box3(new THREE.Vector3(-x / 2, -y / 2, -z / 2), new THREE.Vector3(x / 2, y / 2, z / 2))
}

function fillAfter(view, size, aspect = 16 / 9) {
  const cam = camera(42, aspect)
  const box = boxFromSize(size, size, size)
  applyView(cam, { target: new THREE.Vector3(), update() {} }, box, view)
  return viewFillHeight(cam, box, cam.position.clone().sub(box.getCenter(new THREE.Vector3())).normalize())
}

test("ISO 默认是 3/4 等轴，初次 fit 目标半屏", () => {
  assert.ok(ISO_DIRECTION.x > 0 && ISO_DIRECTION.y > 0 && ISO_DIRECTION.z > 0)
  assert.equal(VIEW_FILL, 0.5)
})

test("applyView 让 mm 级零件占视口高度约 40–60%", () => {
  const fill = fillAfter("iso", 50)
  assert.ok(fill >= 0.4 && fill <= 0.6, `iso mm fill=${fill}`)
})

test("applyView 不把小于 1 的米制 bbox 垫成 1（cascadio/glTF 米）", () => {
  const mm = fillAfter("iso", 50)
  const meters = fillAfter("iso", 0.05)
  assert.ok(meters >= 0.4 && meters <= 0.6, `iso m fill=${meters}`)
  assert.ok(Math.abs(mm - meters) < 0.02, `mm=${mm} m=${meters}`)

  const far = camera()
  const tiny = boxFromSize(0.05, 0.05, 0.05)
  const dist = fitViewDistance(far, tiny, ISO_DIRECTION)
  assert.ok(dist < 1, `meter-scale dist must stay << 1, got ${dist}`)
})

test("front/top/side/fit 同样按投影框适配，ISO 仍是默认方向", () => {
  for (const view of ["front", "top", "side", "iso", "fit"]) {
    const fill = fillAfter(view, 80)
    assert.ok(fill >= 0.4 && fill <= 0.6, `${view} fill=${fill}`)
  }
})

test("只有首次 fit 或显式工具栏请求能改相机，选中导致的 resize 不重复应用", () => {
  assert.equal(shouldApplyRequestedView({
    appliedN: 0,
    requestN: 1,
    hasBox: true,
    hasViewport: true,
  }), true)
  assert.equal(shouldApplyRequestedView({
    appliedN: 1,
    requestN: 1,
    hasBox: true,
    hasViewport: true,
  }), false)
  assert.equal(shouldApplyRequestedView({
    appliedN: 1,
    requestN: 2,
    hasBox: true,
    hasViewport: true,
  }), true)
})

test("定向特征坐标系严格映射 axis 和 x_dir，不退化成世界 AABB", () => {
  const axis = new THREE.Vector3(0, 0, 1)
  const xDir = new THREE.Vector3(Math.SQRT1_2, Math.SQRT1_2, 0)
  const q = orientedQuat(axis, xDir)
  const localX = new THREE.Vector3(1, 0, 0).applyQuaternion(q)
  const localY = new THREE.Vector3(0, 1, 0).applyQuaternion(q)
  assert.ok(localX.distanceTo(xDir) < 1e-9)
  assert.ok(localY.distanceTo(axis) < 1e-9)
})

test("contactShadow 贴在 bbox 底面，far/scale 跟零件尺度走（米/毫米同形）", () => {
  const mm = contactShadowFromBox(boxFromSize(50, 40, 80))
  const meters = contactShadowFromBox(boxFromSize(0.05, 0.04, 0.08))

  assert.ok(mm.position[1] < -20 && mm.position[1] > -20.5, `mm y=${mm.position[1]}`)
  assert.ok(meters.position[1] < -0.02 && meters.position[1] > -0.0205, `m y=${meters.position[1]}`)
  assert.ok(mm.far > 40 && mm.far < 55, `mm far=${mm.far}`)
  assert.ok(meters.far > 0.04 && meters.far < 0.055, `m far=${meters.far}`)
  assert.ok(Math.abs(mm.scale / meters.scale - 1000) < 1e-6)
  assert.ok(meters.far < 0.1, `meter far must stay << 10, got ${meters.far}`)
})

test("FeatureReview 视口 chrome：去掉 ViewCube，只留右上 RGB 轴 + 贴地 ContactShadows", () => {
  assert.doesNotMatch(source, /GizmoViewcube/)
  assert.doesNotMatch(source, /faces=\{\["RIGHT", "LEFT", "TOP", "BOTTOM", "FRONT", "BACK"\]\}/)
  assert.equal([...source.matchAll(/<GizmoHelper/g)].length, 1)
  assert.match(source, /<GizmoViewport/)
  assert.match(source, /axisColors=\{\["#ef4444", "#22c55e", "#3b82f6"\]\}/)
  assert.match(source, /hideNegativeAxes/)
  assert.match(source, /<ContactShadows/)
  assert.match(source, /contactShadowFromBox/)
  assert.match(source, /from "\.\/featureReviewView"/)
  assert.match(source, /camera=\{INITIAL_CAMERA\}/)
  assert.match(source, /appliedRequest\.current = request\.n/)
  assert.doesNotMatch(source, /camera=\{\{\s*position:/)
  assert.doesNotMatch(source, /Math\.max\(size\.y \* 1\.5, 10\)/)
  assert.doesNotMatch(source, /<GizmoHelper[\s\S]*<GizmoHelper/)
})
