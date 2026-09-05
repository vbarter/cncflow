import * as THREE from "three"

export type ViewName = "fit" | "front" | "top" | "side" | "iso"

export const ISO_DIRECTION = new THREE.Vector3(1.35, 0.9, 1.15).normalize()

/** Initial / fit framing: ~half the viewport height, padding on all sides. */
export const VIEW_FILL = 0.5

const _center = new THREE.Vector3()
const _rel = new THREE.Vector3()
const _viewX = new THREE.Vector3()
const _viewY = new THREE.Vector3()
const _up = new THREE.Vector3()
const _dir = new THREE.Vector3()

export function viewDirection(
  view: ViewName,
  camera: THREE.PerspectiveCamera,
  controls: { target?: THREE.Vector3 } | null | undefined,
  center: THREE.Vector3,
): THREE.Vector3 {
  if (view === "fit") {
    _dir.copy(camera.position).sub(controls?.target || center)
    if (_dir.lengthSq() < 1e-8) _dir.copy(ISO_DIRECTION)
    return _dir.normalize()
  }
  if (view === "front") return _dir.set(0, 0, 1)
  if (view === "top") return _dir.set(0, 1, 0)
  if (view === "side") return _dir.set(1, 0, 0)
  return _dir.copy(ISO_DIRECTION)
}

export function projectedHalfExtents(box: THREE.Box3, dir: THREE.Vector3) {
  const viewZ = dir.clone().normalize()
  if (Math.abs(viewZ.y) > 0.99) _up.set(0, 0, -1)
  else _up.set(0, 1, 0)
  _viewX.crossVectors(_up, viewZ).normalize()
  _viewY.crossVectors(viewZ, _viewX).normalize()
  box.getCenter(_center)

  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity
  const { min, max } = box
  for (const x of [min.x, max.x]) {
    for (const y of [min.y, max.y]) {
      for (const z of [min.z, max.z]) {
        _rel.set(x, y, z).sub(_center)
        const px = _rel.dot(_viewX)
        const py = _rel.dot(_viewY)
        if (px < minX) minX = px
        if (px > maxX) maxX = px
        if (py < minY) minY = py
        if (py > maxY) maxY = py
      }
    }
  }
  return {
    halfW: Math.max((maxX - minX) / 2, 1e-6),
    halfH: Math.max((maxY - minY) / 2, 1e-6),
  }
}

export function fitViewDistance(
  camera: THREE.PerspectiveCamera,
  box: THREE.Box3,
  dir: THREE.Vector3,
  fill = VIEW_FILL,
) {
  const { halfW, halfH } = projectedHalfExtents(box, dir)
  const halfFovY = (camera.fov * Math.PI) / 360
  const aspect = Number.isFinite(camera.aspect) && camera.aspect > 1e-4 ? camera.aspect : 1
  const halfFovX = Math.atan(Math.tan(halfFovY) * aspect)
  const distY = halfH / (Math.tan(halfFovY) * fill)
  const distX = halfW / (Math.tan(halfFovX) * 0.9)
  return Math.max(distX, distY, 1e-4)
}

export function viewFillHeight(
  camera: THREE.PerspectiveCamera,
  box: THREE.Box3,
  dir: THREE.Vector3,
) {
  const dist = camera.position.distanceTo(box.getCenter(_center))
  const { halfH } = projectedHalfExtents(box, dir)
  return halfH / (dist * Math.tan((camera.fov * Math.PI) / 360))
}

/** Soft floor under the mesh. Offsets/far follow bbox so meter GLBs do not vanish. */
export function contactShadowFromBox(box: THREE.Box3) {
  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())
  const span = Math.max(size.x, size.y, size.z, 1e-6)
  const footprint = Math.max(size.x, size.z, span * 0.35)
  return {
    position: [
      center.x,
      box.min.y - span * 0.004,
      center.z,
    ] as [number, number, number],
    scale: footprint * 2.6,
    far: size.y + span * 0.08,
  }
}

/**
 * Selection / layout resize must not re-frame. Only an explicit view request
 * (toolbar or the first successful fit) may move OrbitControls.
 */
export function shouldApplyRequestedView(args: {
  appliedN: number
  requestN: number
  hasBox: boolean
  hasViewport: boolean
}) {
  return Boolean(args.hasBox && args.hasViewport && args.requestN > 0 && args.requestN !== args.appliedN)
}

/** Y = feature axis, X = length/u direction in the feature plane. */
export function orientedQuat(axis: THREE.Vector3, xDir?: THREE.Vector3 | null) {
  const y = axis.clone().normalize()
  const x = new THREE.Vector3()
  if (xDir && xDir.lengthSq() > 1e-12) {
    x.copy(xDir).addScaledVector(y, -xDir.dot(y))
  }
  if (x.lengthSq() < 1e-12) {
    x.set(1, 0, 0)
    if (Math.abs(y.dot(x)) > 0.9) x.set(0, 0, 1)
    x.addScaledVector(y, -y.dot(x))
  }
  x.normalize()
  const z = new THREE.Vector3().crossVectors(x, y).normalize()
  x.crossVectors(y, z).normalize()
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z))
}

export function applyView(
  camera: THREE.PerspectiveCamera,
  controls: any,
  box: THREE.Box3,
  view: ViewName,
) {
  const center = box.getCenter(new THREE.Vector3())
  const dir = viewDirection(view, camera, controls, center).clone()
  const dist = fitViewDistance(camera, box, dir)

  camera.up.set(0, 1, 0)
  if (view === "top") camera.up.set(0, 0, -1)
  camera.position.copy(center).add(dir.multiplyScalar(dist))
  camera.near = Math.max(dist / 150, dist / 250, 1e-4)
  camera.far = Math.max(dist * 24, 10)
  camera.updateProjectionMatrix()
  if (controls?.target) {
    controls.target.copy(center)
    controls.update?.()
  }
}
