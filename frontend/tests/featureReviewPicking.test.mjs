import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"
import * as THREE from "three"
import { pickFeatureAtPoint } from "../src/components/FeatureReview.tsx"

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

test("CAD 表面点击按分析几何选择最近特征，重叠时孔优先于面", () => {
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
    pickFeatureAtPoint([face, hole], new THREE.Vector3(3.8, 0, 0)),
    "hole-8",
  )
  assert.equal(
    pickFeatureAtPoint([face, hole], new THREE.Vector3(30, 20, 0)),
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

test("CAD 实体接入点击处理，特征树点击链保持不变", () => {
  assert.match(source, /<primitive[\s\S]*onClick=\{\(event: any\)/)
  assert.match(source, /onPick\(event\.point\)/)
  assert.match(source, /onClick=\{\(\) => setPicked\(f\.feature_id\)\}/)
})
