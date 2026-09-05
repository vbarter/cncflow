import * as THREE from "three"

/** Drop overlays (ContactShadows plane, Gizmo/Hud) out of the pick ray. */
export function disableRaycast(root: THREE.Object3D | null | undefined) {
  if (!root) return
  const mute = (object: THREE.Object3D) => {
    object.raycast = () => null
  }
  mute(root)
  root.traverse(mute)
}

export function pickBestFeature(
  intersections: Array<{ object?: THREE.Object3D | null; distance?: number }> | undefined,
): string | null {
  let best: { id: string; rank: number; dist: number } | null = null
  for (const hit of intersections || []) {
    let object = hit.object as THREE.Object3D | null
    while (object) {
      const id = object.userData?.featureId
      if (id) {
        const rank = Number(object.userData.pickRank ?? 9)
        const dist = Number(hit.distance ?? 0)
        if (!best || rank < best.rank || (rank === best.rank && dist < best.dist)) {
          best = { id, rank, dist }
        }
        break
      }
      object = object.parent
    }
  }
  return best?.id || null
}
