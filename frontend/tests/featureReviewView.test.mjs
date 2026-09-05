import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import * as THREE from "three"
import {
  ISO_DIRECTION,
  VIEW_FILL,
  applyView,
  fitViewDistance,
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

test("FeatureReview 视口 chrome：右上角仅保留紧凑 RGB 坐标轴", () => {
  assert.doesNotMatch(source, /GizmoViewcube/)
  assert.equal([...source.matchAll(/<GizmoHelper/g)].length, 1)
  assert.match(source, /<GizmoViewport/)
  assert.match(source, /axisColors=\{\["#ef4444",\s*"#22c55e",\s*"#3b82f6"\]\}/)
  assert.match(source, /axisScale=\{\[0\.72,\s*0\.035,\s*0\.035\]\}/)
  assert.match(source, /hideNegativeAxes/)
  assert.match(source, /from "\.\/featureReviewView"/)
  assert.doesNotMatch(source, /<GizmoHelper[\s\S]*<GizmoHelper/)
})

test("FeatureReview 地面阴影按 bbox 比例贴住零件，兼容 mm 与 m 单位", () => {
  assert.match(source, /<ContactShadows/)
  assert.match(source, /box\.min\.y - offset/)
  assert.match(source, /width=\{shadow\.width\}/)
  assert.match(source, /height=\{shadow\.height\}/)
  assert.match(source, /opacity=\{0\.48\}/)
  assert.doesNotMatch(source, /Math\.max\(size\.y \* 0\.015,\s*0\.08\)/)
  assert.doesNotMatch(source, /Math\.max\(size\.y \* 1\.5,\s*10\)/)
})
