import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import * as THREE from "three"
import {
  featureHighlightSignature,
  featureUnitScaleForBox,
  pickFeatureAtPoint,
} from "../src/components/FeatureReview.tsx"

const source = await readFile(
  new URL("../src/components/FeatureReview.tsx", import.meta.url),
  "utf8",
)

const face = {
  feature_id: "face-top",
  type: "face",
  location: { x: 0, y: 0, z: 0 },
  axis: { x: 0, y: 0, z: 1 },
  length: 80,
  width: 60,
}

test("CAD 表面点击在孔缘容差内优先选孔，离开孔区后选面", () => {
  const hole = {
    feature_id: "hole-8",
    type: "hole",
    pose: {
      origin: { x: 0, y: 0, z: 0 },
      axis: { x: 0, y: 0, z: 1 },
      length_mm: 12,
      diameter_mm: 8,
    },
  }

  assert.equal(
    pickFeatureAtPoint([face, hole], new THREE.Vector3(5.5, 0, 0)),
    "hole-8",
  )
  assert.equal(
    pickFeatureAtPoint([face, hole], new THREE.Vector3(30, 20, 0)),
    "face-top",
  )
})

test("cascadio 米制 mesh 点击点与 mm 特征 pose 自动对齐", () => {
  const meterBox = new THREE.Box3(
    new THREE.Vector3(-0.064, -0.047, -0.006),
    new THREE.Vector3(0.064, 0.047, 0.006),
  )
  const mmBox = new THREE.Box3(
    new THREE.Vector3(-64, -47, -6),
    new THREE.Vector3(64, 47, 6),
  )
  const hole = {
    feature_id: "hole-mm",
    type: "hole",
    pose: {
      origin: { x: 20, y: 0, z: -6 },
      axis: { x: 0, y: 0, z: 1 },
      length_mm: 12,
      diameter_mm: 8,
    },
  }

  assert.equal(featureUnitScaleForBox([face, hole], meterBox), 0.001)
  assert.equal(featureUnitScaleForBox([face, hole], mmBox), 1)
  assert.equal(
    pickFeatureAtPoint([face, hole], new THREE.Vector3(0.0245, 0, 0), 0.001),
    "hole-mm",
  )
})

test("同平面重叠 face 选较小局部区域，不粘在 generic face", () => {
  const localFace = {
    feature_id: "face-local",
    type: "face",
    location: { x: 20, y: 0, z: 0 },
    axis: { x: 0, y: 0, z: 1 },
    length: 12,
    width: 10,
  }

  assert.equal(
    pickFeatureAtPoint([face, localFace], new THREE.Vector3(20, 0, 0)),
    "face-local",
  )
  assert.equal(
    pickFeatureAtPoint([face, localFace], new THREE.Vector3(-30, 20, 0)),
    "face-top",
  )
})

test("外圆生成可高亮圆柱壳，侧壁可选且不会吞掉内侧面", () => {
  const outerCylinder = {
    feature_id: "od-8",
    type: "outer_cylinder",
    diameter_mm: 50,
    depth_mm: 12,
    location: { x: 0, y: 0, z: 0 },
    axis: { x: 0, y: 0, z: 1 },
  }

  assert.equal(
    pickFeatureAtPoint([face, outerCylinder], new THREE.Vector3(25, 0, 0)),
    "od-8",
  )
  assert.equal(
    pickFeatureAtPoint([face, outerCylinder], new THREE.Vector3(0, 0, 0)),
    "face-top",
  )
})

test("CAD 表面点击可选择最近的槽代理，并忽略无 pose 特征", () => {
  const slot = {
    feature_id: "slot-open",
    type: "slot",
    location: { x: 20, y: 0, z: -2 },
    axis: { x: 0, y: 0, z: 1 },
    length: 16,
    width: 6,
    depth: 4,
  }
  const unavailable = { feature_id: "unknown", type: "hole" }

  assert.equal(
    pickFeatureAtPoint([unavailable, face, slot], new THREE.Vector3(20, 0, 0)),
    "slot-open",
  )
  assert.equal(pickFeatureAtPoint([unavailable], new THREE.Vector3()), null)
})

test("CAD 实体统一负责拾取；树、参数和高亮共享 picked 状态", () => {
  assert.match(source, /<primitive[\s\S]*onClick=\{\(event: any\)/)
  assert.match(source, /onPick\(event\.point\)/)
  assert.match(source, /onClick=\{\(\) => setPicked\(f\.feature_id\)\}/)
  assert.doesNotMatch(source, /pickBestFeature/)
  assert.match(source, /selected=\{f\.feature_id === picked\}/)
  assert.match(source, /color: "#f97316"[\s\S]*depthTest: true/)
  assert.match(source, /<group scale=\{unitScale\}>/)
  assert.match(source, /t === "outer_cylinder"/)
  assert.match(source, /new THREE\.ExtrudeGeometry/)
  assert.match(source, /roundedRectangle\(pose\.size\[0\], pose\.size\[2\], pose\.cornerRadius\)/)
  assert.match(source, /new THREE\.PlaneGeometry/)
  assert.match(source, /Boolean\(pose\.shell\)/)
  assert.doesNotMatch(source, /BoxGeometry/)
})

test("等价 feature clone 共享高亮签名，几何变化才触发资源重建", () => {
  const slot = {
    feature_id: "slot-stable",
    type: "slot",
    location: { x: 20, y: 4, z: -2 },
    axis: { x: 0, y: 0, z: 1 },
    x_dir: { x: 1, y: 0, z: 0 },
    length: 16,
    width: 6,
    depth: 4,
    corner_radius: 2,
  }
  const cloned = structuredClone(slot)
  assert.equal(featureHighlightSignature(cloned), featureHighlightSignature(slot))
  assert.notEqual(
    featureHighlightSignature({ ...cloned, depth: 5 }),
    featureHighlightSignature(slot),
  )
  assert.match(source, /useMemo\(\(\) => makeHighlightResources\(pose\), \[signature\]\)/)
  assert.match(source, /const FeatureMark = React\.memo/)
  assert.doesNotMatch(source, /makeFeatureGeometry\(pose\), \[pose\]/)
})

test("高亮填充避开共面 depth fighting，几何、边线和材质统一释放", () => {
  assert.match(source, /polygonOffset: true/)
  assert.match(source, /polygonOffsetFactor: -2/)
  assert.match(source, /polygonOffsetUnits: -2/)
  assert.match(source, /resources\.geometry\.dispose\(\)/)
  assert.match(source, /resources\.edges\.dispose\(\)/)
  assert.match(source, /resources\.fill\.dispose\(\)/)
  assert.match(source, /resources\.outline\.dispose\(\)/)
})
