import assert from "node:assert/strict"
import test from "node:test"
import * as THREE from "three"
import { disableRaycast, pickBestFeature } from "../src/components/featureReviewPick.ts"

test("pickBestFeature 忽略无 featureId 的阴影/地面 hit，圆柱优先于槽盒", () => {
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(80, 80))
  const slot = new THREE.Mesh(new THREE.BoxGeometry(4, 2, 4))
  slot.userData = { featureId: "slot-1", pickRank: 1 }
  const hole = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 4, 12))
  hole.userData = { featureId: "hole-1", pickRank: 0 }

  assert.equal(pickBestFeature([
    { object: shadow, distance: 1 },
    { object: slot, distance: 2 },
    { object: hole, distance: 3 },
  ]), "hole-1")
  assert.equal(pickBestFeature([{ object: shadow, distance: 1 }]), null)
})

test("disableRaycast 让接触阴影平面不再挡住特征 mesh", () => {
  const scene = new THREE.Scene()
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(40, 40))
  plane.rotation.x = -Math.PI / 2
  scene.add(plane)

  const mark = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2))
  mark.userData = { featureId: "pocket-1", pickRank: 1 }
  mark.position.set(0, 1, 0)
  scene.add(mark)

  const raycaster = new THREE.Raycaster()
  raycaster.set(new THREE.Vector3(0, 8, 0), new THREE.Vector3(0, -1, 0))

  const blocked = raycaster.intersectObject(scene, true)
  assert.ok(blocked.length >= 2, "unmuted plane must sit on the pick ray")

  disableRaycast(plane)
  const hits = raycaster.intersectObject(scene, true)
  assert.equal(hits.length, 1)
  assert.equal(pickBestFeature(hits), "pocket-1")
})
