import React, { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { Canvas, useThree } from "@react-three/fiber"
import {
  ContactShadows,
  GizmoHelper,
  GizmoViewport,
  OrbitControls,
} from "@react-three/drei"
import { Maximize2, Scissors } from "lucide-react"
import * as THREE from "three"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"
import { API } from "../api"
import { ProcessStepParameters } from "./ProcessSequenceEditor"
import {
  applyView,
  contactShadowFromBox,
  orientedQuat,
  shouldApplyRequestedView,
  type ViewName,
} from "./featureReviewView"

type Feat = any

type Pose =
  | { kind: "cyl"; origin: THREE.Vector3; axis: THREE.Vector3; length: number; diameter: number; centered: boolean; shell?: boolean }
  | { kind: "plate"; origin: THREE.Vector3; axis: THREE.Vector3; xDir: THREE.Vector3 | null; size: [number, number, number] }
  | { kind: "box"; origin: THREE.Vector3; axis: THREE.Vector3; xDir: THREE.Vector3 | null; size: [number, number, number]; cornerRadius: number; depthFromOrigin: boolean }
  | { kind: "surface"; origin: THREE.Vector3; radius: number }

const INITIAL_CAMERA = {
  position: [72, 48, 62] as [number, number, number],
  fov: 42,
  near: 0.1,
  far: 4000,
}

const CANVAS_GL = {
  antialias: true,
  alpha: true,
  localClippingEnabled: true,
}

function holeLabel(ht: string | undefined) {
  if (ht === "through" || ht === "通孔") return "通孔"
  if (ht === "blind" || ht === "盲孔") return "盲孔"
  return ht || "—"
}

function xyz(v: any): THREE.Vector3 | null {
  if (!v) return null
  if (typeof v.x === "number") return new THREE.Vector3(v.x, v.y, v.z)
  return null
}

function num(...vals: any[]): number | null {
  for (const v of vals) {
    if (v == null || v === "") continue
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

function featType(f: Feat): string {
  return String(f.type || f.kind || f.feature_type || "").toLowerCase()
}

function featureXDir(f: Feat) {
  return (
    xyz(f.pose?.x_dir)
    || xyz(f.pose?.x_axis)
    || xyz(f.x_dir)
    || xyz(f.x_axis)
    || xyz(f.length_axis)
  )
}

export function isReviewTreeFeature(feature: Feat): boolean {
  const id = String(feature?.feature_id || feature?.id || "")
  return feature?.subtype !== "cylindrical_candidate" && !id.startsWith("cylinder-")
}

function poseOf(f: Feat): Pose | null {
  const t = featType(f)
  const dim = f.dimensions || {}
  const origin = xyz(f.pose?.origin) || xyz(f.location) || xyz(f.center) || xyz(f.position)
  const axisRaw = xyz(f.pose?.axis) || xyz(f.axis)
  const axis = (axisRaw || new THREE.Vector3(0, 0, 1)).clone().normalize()
  const xDir = featureXDir(f)

  if (t === "hole" || t === "thread" || t === "outer_cylinder") {
    if (!origin) return null
    const diameter = num(f.pose?.diameter_mm, f.diameter_mm, f.nominal_d, dim.diameter_mm) || 1
    const length = num(f.pose?.length_mm, f.depth_mm, f.thread_length, dim.thread_length, dim.depth_mm) || 1
    return {
      kind: "cyl",
      origin,
      axis,
      length,
      diameter,
      centered: !f.pose?.origin,
      shell: t === "outer_cylinder",
    }
  }

  if (t === "face") {
    if (!origin) return null
    const L = num(f.length, dim.length) || 8
    const W = num(f.width, dim.width) || 8
    const thickness = Math.max(Math.min(L, W) * 0.008, 0.05)
    return { kind: "plate", origin, axis, xDir, size: [L, thickness, W] }
  }

  if (t === "pocket" || t === "slot") {
    if (!origin) return null
    const L = num(f.length, dim.length) || 8
    const W = num(f.width, dim.width) || 8
    const H = num(f.depth, dim.depth, f.height, dim.height) || 4
    const cornerRadius = num(f.corner_radius, dim.corner_radius) ?? 0
    return { kind: "box", origin, axis, xDir, size: [L, H, W], cornerRadius, depthFromOrigin: true }
  }

  if (t === "step") {
    if (!origin) return null
    const L = num(f.length, dim.length) || 8
    const W = num(f.width, dim.width) || 8
    const H = num(f.height, dim.height, f.depth, dim.depth) || 4
    return { kind: "box", origin, axis, xDir, size: [L, H, W], cornerRadius: 0, depthFromOrigin: false }
  }

  if (t === "surface") {
    if (!origin) return null
    const radius = num(f.curvature_radius, dim.curvature_radius, f.radius_mm, f.radius, f.R, dim.R) || 8
    return { kind: "surface", origin, radius }
  }

  return null
}

function useGltfScene(url: string) {
  const [scene, setScene] = useState<THREE.Object3D | null>(null)
  useEffect(() => {
    let live = true
    const loader = new GLTFLoader()
    loader.load(url, (gltf) => { if (live) setScene(gltf.scene) }, undefined, () => { if (live) setScene(null) })
    return () => { live = false }
  }, [url])
  return scene
}

type ViewRequest = { view: ViewName; n: number }

function ViewRig({
  box,
  request,
  onApplied,
}: {
  box: THREE.Box3 | null
  request: ViewRequest | null
  onApplied: (n: number) => void
}) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera
  const controls = useThree((s) => s.controls)
  const size = useThree((s) => s.size)
  const appliedRequest = useRef(0)
  useLayoutEffect(() => {
    if (!controls || !request || !shouldApplyRequestedView({
      appliedN: appliedRequest.current,
      requestN: request.n,
      hasBox: Boolean(box),
      hasViewport: size.width > 0 && size.height > 0,
    })) return
    camera.aspect = size.width / size.height
    applyView(camera, controls, box!, request.view)
    appliedRequest.current = request.n
    onApplied(request.n)
  }, [box, request, camera, controls, size.width, size.height, onApplied])
  return null
}

function CadAxesGizmo() {
  return (
    <GizmoHelper alignment="top-right" margin={[64, 64]} renderPriority={1}>
      <GizmoViewport
        axisColors={["#ef4444", "#22c55e", "#3b82f6"]}
        labelColor="#ffffff"
        axisHeadScale={0.82}
        hideNegativeAxes
      />
    </GizmoHelper>
  )
}

function CadBody({
  url, clipPlane, onBox, onPick,
}: {
  url: string
  clipPlane: THREE.Plane | null
  onBox: (box: THREE.Box3) => void
  onPick: (point: THREE.Vector3) => void
}) {
  const scene = useGltfScene(url)
  const root = useMemo(() => {
    if (!scene) return null
    const cloned = scene.clone(true)
    cloned.traverse((o) => {
      if (!(o instanceof THREE.Mesh) || !o.geometry) return
      o.castShadow = true
      o.receiveShadow = true
      o.material = new THREE.MeshStandardMaterial({
        color: 0x98a2ad,
        metalness: 0.08,
        roughness: 0.62,
        side: THREE.DoubleSide,
      })
      const edges = new THREE.EdgesGeometry(o.geometry, 32)
      const lines = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({
          color: 0x475569,
          transparent: true,
          opacity: 0.24,
        }),
      )
      lines.raycast = () => {}
      o.add(lines)
    })
    return cloned
  }, [scene])

  useEffect(() => {
    if (!root) return
    const box = new THREE.Box3().setFromObject(root)
    if (!box.isEmpty()) onBox(box)
  }, [root, onBox])

  useEffect(() => {
    if (!root) return
    const planes = clipPlane ? [clipPlane] : []
    root.traverse((o) => {
      const mats = []
      if (o instanceof THREE.Mesh) mats.push(...(Array.isArray(o.material) ? o.material : [o.material]))
      if (o instanceof THREE.LineSegments) mats.push(...(Array.isArray(o.material) ? o.material : [o.material]))
      for (const m of mats) {
        if (!m) continue
        m.clippingPlanes = planes
        m.clipShadows = true
        m.needsUpdate = true
      }
    })
  }, [root, clipPlane])

  if (!root) return null
  return (
    <primitive
      object={root}
      onClick={(event: any) => {
        if (event.delta > 2) return
        event.stopPropagation()
        onPick(event.point)
      }}
    />
  )
}

function SectionHelper({ box, t }: { box: THREE.Box3; t: number }) {
  const size = box.getSize(new THREE.Vector3())
  const center = box.getCenter(new THREE.Vector3())
  const x = box.min.x + size.x * t
  return (
    <mesh position={[x, center.y, center.z]} rotation={[0, Math.PI / 2, 0]} raycast={() => {}}>
      <planeGeometry args={[Math.max(size.z, 1) * 1.06, Math.max(size.y, 1) * 1.06]} />
      <meshBasicMaterial color="#2563eb" transparent opacity={0.12} side={THREE.DoubleSide} depthWrite={false} />
    </mesh>
  )
}

function distanceOutside(value: number, min: number, max: number) {
  return value < min ? min - value : value > max ? value - max : 0
}

function distanceToPose(point: THREE.Vector3, pose: Pose) {
  const rel = point.clone().sub(pose.origin)
  if (pose.kind === "cyl") {
    const axial = rel.dot(pose.axis)
    const radial = rel.addScaledVector(pose.axis, -axial).length()
    const min = pose.centered ? -pose.length / 2 : 0
    const max = pose.centered ? pose.length / 2 : pose.length
    return Math.hypot(
      pose.shell
        ? Math.abs(radial - pose.diameter / 2)
        : Math.max(0, radial - pose.diameter / 2),
      distanceOutside(axial, min, max),
    )
  }

  if (pose.kind === "surface") {
    return Math.hypot(
      distanceOutside(rel.x, -4, 4),
      distanceOutside(rel.y, -4, 4),
      distanceOutside(rel.z, -4, 4),
    )
  }

  rel.applyQuaternion(orientedQuat(pose.axis, pose.xDir).invert())
  const minY = pose.kind === "box" && pose.depthFromOrigin ? 0 : -pose.size[1] / 2
  const maxY = pose.kind === "box" && pose.depthFromOrigin ? pose.size[1] : pose.size[1] / 2
  return Math.hypot(
    distanceOutside(rel.x, -pose.size[0] / 2, pose.size[0] / 2),
    distanceOutside(rel.y, minY, maxY),
    distanceOutside(rel.z, -pose.size[2] / 2, pose.size[2] / 2),
  )
}

function poseSpan(pose: Pose) {
  if (pose.kind === "cyl") return Math.max(pose.length, pose.diameter)
  if (pose.kind === "surface") return Math.min(pose.radius * 2, 32)
  return Math.max(...pose.size)
}

/**
 * cascadio follows glTF's metre convention while analysis coordinates are mm.
 * The fallback exporter currently keeps mm. Match their extents instead of
 * hard-coding either exporter, so marks and mesh hit points share one space.
 */
export function featureUnitScaleForBox(features: Feat[], box: THREE.Box3 | null) {
  if (!box || box.isEmpty()) return 1
  const meshSize = box.getSize(new THREE.Vector3())
  const meshSpan = Math.max(meshSize.x, meshSize.y, meshSize.z)
  const featureSpan = features.reduce((largest, feature) => {
    const pose = poseOf(feature)
    return pose ? Math.max(largest, poseSpan(pose)) : largest
  }, 0)
  if (!(meshSpan > 0) || !(featureSpan > 0)) return 1

  const observed = meshSpan / featureSpan
  const candidates = [0.001, 1, 1000]
  return candidates.reduce((best, candidate) => (
    Math.abs(Math.log(observed / candidate)) < Math.abs(Math.log(observed / best))
      ? candidate
      : best
  ), 1)
}

function featurePickRank(feature: Feat) {
  const type = featType(feature)
  if (type === "thread") return 0
  if (type === "hole") return 1
  if (type === "slot" || type === "pocket") return 2
  if (type === "step") return 3
  if (type === "surface" || type === "outer_cylinder") return 4
  return 5
}

function poseFootprint(pose: Pose) {
  if (pose.kind === "cyl") return Math.PI * (pose.diameter / 2) ** 2
  if (pose.kind === "surface") return Math.PI * Math.min(pose.radius, 16) ** 2
  return pose.size[0] * pose.size[2]
}

function posePickTolerance(pose: Pose) {
  if (pose.kind === "cyl") {
    return pose.shell
      ? Math.max(0.5, pose.diameter * 0.02)
      : Math.max(0.5, pose.diameter * 0.35)
  }
  if (pose.kind === "box") return Math.max(0.5, Math.min(pose.size[0], pose.size[2]) * 0.25)
  if (pose.kind === "surface") return Math.max(0.5, Math.min(pose.radius, 16) * 0.15)
  return Math.max(0.25, Math.min(pose.size[0], pose.size[2]) * 0.01)
}

type PickCandidate = {
  id: string
  rank: number
  distance: number
  normalizedDistance: number
  footprint: number
}

function betterPick(candidate: PickCandidate, best: PickCandidate | null) {
  if (!best) return true
  if (candidate.rank !== best.rank) return candidate.rank < best.rank
  if (Math.abs(candidate.normalizedDistance - best.normalizedDistance) > 1e-6) {
    return candidate.normalizedDistance < best.normalizedDistance
  }
  if (Math.abs(candidate.footprint - best.footprint) > 1e-6) {
    return candidate.footprint < best.footprint
  }
  return candidate.distance < best.distance
}

export function pickFeatureAtPoint(
  features: Feat[],
  meshPoint: THREE.Vector3,
  featureUnitScale = 1,
): string | null {
  const point = meshPoint.clone().divideScalar(featureUnitScale || 1)
  let snapped: PickCandidate | null = null
  let nearest: PickCandidate | null = null
  for (const feature of features) {
    const pose = poseOf(feature)
    const id = feature?.feature_id
    if (!pose || !id) continue
    const distance = distanceToPose(point, pose)
    const tolerance = posePickTolerance(pose)
    const candidate = {
      id,
      rank: featurePickRank(feature),
      distance,
      normalizedDistance: distance / tolerance,
      footprint: poseFootprint(pose),
    }
    if (
      !nearest
      || distance < nearest.distance - 1e-6
      || (Math.abs(distance - nearest.distance) <= 1e-6 && betterPick(candidate, nearest))
    ) {
      nearest = candidate
    }
    if (distance <= tolerance && betterPick(candidate, snapped)) snapped = candidate
  }
  return snapped?.id || nearest?.id || null
}

function roundedRectangle(length: number, width: number, cornerRadius: number) {
  const hx = length / 2
  const hz = width / 2
  const r = Math.max(0, Math.min(cornerRadius, hx, hz))
  const shape = new THREE.Shape()
  shape.moveTo(-hx + r, -hz)
  shape.lineTo(hx - r, -hz)
  shape.quadraticCurveTo(hx, -hz, hx, -hz + r)
  shape.lineTo(hx, hz - r)
  shape.quadraticCurveTo(hx, hz, hx - r, hz)
  shape.lineTo(-hx + r, hz)
  shape.quadraticCurveTo(-hx, hz, -hx, hz - r)
  shape.lineTo(-hx, -hz + r)
  shape.quadraticCurveTo(-hx, -hz, -hx + r, -hz)
  return shape
}

function makeFeatureGeometry(pose: Pose) {
  if (pose.kind === "cyl") {
    return new THREE.CylinderGeometry(
      pose.diameter / 2,
      pose.diameter / 2,
      pose.length,
      48,
      1,
      Boolean(pose.shell),
    )
  }
  if (pose.kind === "plate") {
    const geometry = new THREE.PlaneGeometry(pose.size[0], pose.size[2])
    geometry.rotateX(-Math.PI / 2)
    return geometry
  }
  if (pose.kind === "box") {
    const geometry = new THREE.ExtrudeGeometry(
      roundedRectangle(pose.size[0], pose.size[2], pose.cornerRadius),
      {
        depth: pose.size[1],
        bevelEnabled: false,
        curveSegments: 16,
        steps: 1,
      },
    )
    geometry.rotateX(-Math.PI / 2)
    geometry.translate(0, -pose.size[1] / 2, 0)
    return geometry
  }
  return new THREE.SphereGeometry(Math.min(pose.radius, 16), 24, 16)
}

function vectorSignature(vector: THREE.Vector3 | null | undefined) {
  return vector ? `${vector.x},${vector.y},${vector.z}` : "-"
}

function poseSignature(pose: Pose) {
  const base = `${pose.kind}|${vectorSignature(pose.origin)}`
  if (pose.kind === "cyl") {
    return `${base}|${vectorSignature(pose.axis)}|${pose.length}|${pose.diameter}|${pose.centered}|${Boolean(pose.shell)}`
  }
  if (pose.kind === "surface") return `${base}|${pose.radius}`
  const oriented = `${base}|${vectorSignature(pose.axis)}|${vectorSignature(pose.xDir)}|${pose.size.join(",")}`
  if (pose.kind === "box") {
    return `${oriented}|${pose.cornerRadius}|${pose.depthFromOrigin}`
  }
  return oriented
}

export function featureHighlightSignature(feature: Feat) {
  const pose = poseOf(feature)
  return pose ? `${String(feature?.feature_id || "")}|${poseSignature(pose)}` : null
}

type HighlightResources = {
  geometry: THREE.BufferGeometry
  edges: THREE.EdgesGeometry
  fill: THREE.MeshBasicMaterial
  outline: THREE.LineBasicMaterial
}

function makeHighlightResources(pose: Pose): HighlightResources {
  const geometry = makeFeatureGeometry(pose)
  return {
    geometry,
    edges: new THREE.EdgesGeometry(geometry, 20),
    fill: new THREE.MeshBasicMaterial({
      color: "#f97316",
      transparent: true,
      opacity: pose.kind === "plate" ? 0.3 : pose.kind === "cyl" && pose.shell ? 0.34 : 0.4,
      depthTest: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      toneMapped: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    }),
    outline: new THREE.LineBasicMaterial({
      color: "#ea580c",
      transparent: true,
      opacity: 0.9,
      depthTest: true,
      toneMapped: false,
    }),
  }
}

function disposeHighlightResources(resources: HighlightResources) {
  resources.geometry.dispose()
  resources.edges.dispose()
  resources.fill.dispose()
  resources.outline.dispose()
}

const FeatureHighlight = React.memo(function FeatureHighlight({
  pose,
  signature,
}: {
  pose: Pose
  signature: string
}) {
  const resources = useMemo(() => makeHighlightResources(pose), [signature])
  useEffect(
    () => () => disposeHighlightResources(resources),
    [resources],
  )
  return (
    <>
      <mesh renderOrder={20} raycast={() => {}}>
        <primitive object={resources.geometry} attach="geometry" />
        <primitive object={resources.fill} attach="material" />
      </mesh>
      <lineSegments renderOrder={21} raycast={() => {}}>
        <primitive object={resources.edges} attach="geometry" />
        <primitive object={resources.outline} attach="material" />
      </lineSegments>
    </>
  )
})

type FeatureMarkProps = {
  feat: Feat
  selected: boolean
  unitScale: number
}

const FeatureMark = React.memo(function FeatureMark({
  feat,
  selected,
  unitScale,
}: FeatureMarkProps) {
  const signature = featureHighlightSignature(feat)
  const pose = useMemo(() => poseOf(feat), [signature])
  if (!pose || !selected) return null
  const q = pose.kind === "surface"
    ? undefined
    : orientedQuat(pose.axis, "xDir" in pose ? pose.xDir : null)
  const mid = pose.kind === "cyl"
    ? (pose.centered ? pose.origin : pose.origin.clone().add(pose.axis.clone().multiplyScalar(pose.length / 2)))
    : pose.kind === "box" && pose.depthFromOrigin
      ? pose.origin.clone().add(pose.axis.clone().multiplyScalar(pose.size[1] / 2))
      : pose.origin

  return (
    <group scale={unitScale}>
      <group position={mid} quaternion={q}>
        <FeatureHighlight pose={pose} signature={signature!} />
      </group>
    </group>
  )
}, (previous, next) => (
  previous.selected === next.selected
  && (!next.selected || (
    previous.unitScale === next.unitScale
    && featureHighlightSignature(previous.feat) === featureHighlightSignature(next.feat)
  ))
))

function inspectorFields(f: Feat) {
  const dim = f.dimensions || {}
  const type = featType(f)
  const height = type === "thread"
    ? f.thread_length ?? dim.thread_length ?? f.depth_mm ?? dim.depth_mm
    : type === "hole"
      ? f.depth_mm ?? dim.depth_mm
      : type === "step"
        ? f.height ?? dim.height ?? f.depth ?? dim.depth ?? f.depth_mm ?? dim.depth_mm
        : f.depth ?? dim.depth ?? f.height ?? dim.height ?? f.depth_mm ?? dim.depth_mm
  return {
    d: f.diameter_mm ?? f.nominal_d ?? dim.diameter_mm,
    l: f.length ?? dim.length,
    w: f.width ?? dim.width,
    h: height,
    r: f.curvature_radius ?? dim.curvature_radius ?? f.radius_mm ?? f.radius ?? f.R ?? dim.R,
    orient: f.position_type || f.face_position || dim.face_position || f.position || dim.position,
  }
}

type DimensionField = {
  key: string
  label: string
  value: unknown
  prefix?: string
}

function editableDimensions(f: Feat): DimensionField[] {
  const fields = inspectorFields(f)
  const type = featType(f)
  if (type === "hole") return [
    { key: "diameter_mm", label: "D", value: fields.d, prefix: "Ø" },
    { key: "depth_mm", label: "H", value: fields.h },
  ]
  if (type === "thread") return [
    { key: "diameter_mm", label: "D", value: fields.d, prefix: "Ø" },
    { key: "thread_length", label: "H", value: fields.h },
  ]
  if (type === "slot" || type === "pocket") return [
    { key: "length", label: "L", value: fields.l },
    { key: "width", label: "W", value: fields.w },
    { key: "depth", label: "H", value: fields.h },
  ]
  if (type === "face") return [
    { key: "length", label: "L", value: fields.l },
    { key: "width", label: "W", value: fields.w },
  ]
  if (type === "step") return [
    { key: "length", label: "L", value: fields.l },
    { key: "width", label: "W", value: fields.w },
    { key: "height", label: "H", value: fields.h },
  ]
  return []
}

function displayValue(value: unknown) {
  if (value == null || value === "") return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function processName(step: any) {
  return step.name || step.process || step.op || step.step_id || "工序"
}

export function ViewerToolbar({
  view, section, sectionT, onView, onSection, onSectionT,
}: {
  view: ViewName | null
  section: boolean
  sectionT: number
  onView: (v: ViewName) => void
  onSection: (on: boolean) => void
  onSectionT: (t: number) => void
}) {
  const btn = (id: ViewName, label: string, title: string) => (
    <button
      type="button"
      className={`flex h-7 min-w-7 items-center justify-center rounded-md px-2 text-[11px] font-medium transition-colors ${view === id ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}
      onClick={() => onView(id)}
      aria-label={title}
      title={title}
    >
      {label}
    </button>
  )
  return (
    <div
      className="absolute left-3 top-3 z-10 flex items-center gap-0.5 rounded-lg border border-white/80 bg-white/90 p-1 shadow-md shadow-slate-900/10 backdrop-blur"
      onPointerDown={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="flex size-7 items-center justify-center rounded-md text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
        onClick={() => onView("fit")}
        aria-label="适应窗口"
        title="适应窗口"
      >
        <Maximize2 size={14} strokeWidth={1.8} />
      </button>
      <span className="mx-0.5 h-4 w-px bg-slate-200" aria-hidden />
      {btn("front", "前", "前视图")}
      {btn("top", "顶", "顶视图")}
      {btn("side", "侧", "侧视图")}
      {btn("iso", "ISO", "等轴视图")}
      <span className="mx-0.5 h-4 w-px bg-slate-200" aria-hidden />
      <button
        type="button"
        className={`flex size-7 items-center justify-center rounded-md transition-colors ${section ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}
        onClick={() => onSection(!section)}
        aria-label="剖切"
        title="剖切"
      >
        <Scissors size={14} strokeWidth={1.8} />
      </button>
      {section && (
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(sectionT * 100)}
          onChange={(e) => onSectionT(Number(e.target.value) / 100)}
          className="mx-1 h-7 w-16 accent-blue-600"
          aria-label="剖切位置"
        />
      )}
    </div>
  )
}

export function FeatureReview({
  partId,
  features,
  processSequence,
  meshAvailable,
  locked,
  busy,
  onToggle,
  onPatchFeature,
  onPatchProcess,
}: {
  partId: string
  features: Feat[]
  processSequence: any[]
  meshAvailable: boolean
  locked: boolean
  busy: boolean
  onToggle: (id: string, checked: boolean) => void
  onPatchFeature: (body: object) => Promise<void>
  onPatchProcess: (body: object) => Promise<void>
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const [dimensionDrafts, setDimensionDrafts] = useState<Record<string, string>>({})
  const [box, setBox] = useState<THREE.Box3 | null>(null)
  const [view, setView] = useState<ViewName | null>("iso")
  const [viewReq, setViewReq] = useState<ViewRequest | null>(null)
  const [section, setSection] = useState(false)
  const [sectionT, setSectionT] = useState(0.5)
  const fitted = useRef(false)
  const viewRequestN = useRef(0)
  const orbitTarget = useMemo(() => new THREE.Vector3(), [])
  const meshUrl = `${API}/parts/${partId}/mesh`
  const visibleFeatures = useMemo(
    () => features.filter(isReviewTreeFeature),
    [features],
  )
  const selected = visibleFeatures.find((f) => f.feature_id === picked)
  const pickables = useMemo(
    () => visibleFeatures.filter((f) => poseOf(f)),
    [visibleFeatures],
  )
  const featureUnitScale = useMemo(
    () => featureUnitScaleForBox(pickables, box),
    [pickables, box],
  )
  const pickSurface = useCallback((point: THREE.Vector3) => {
    const id = pickFeatureAtPoint(pickables, point, featureUnitScale)
    if (id) setPicked(id)
  }, [pickables, featureUnitScale])
  const fields = selected ? inspectorFields(selected) : null
  const dimensions = selected ? editableDimensions(selected) : []
  const selectedSteps = useMemo(
    () => processSequence.filter((step) => step.feature_id === picked),
    [processSequence, picked],
  )
  const onBox = useCallback((b: THREE.Box3) => setBox(b.clone()), [])
  const requestView = useCallback((nextView: ViewName) => {
    setView(nextView)
    setViewReq({ view: nextView, n: ++viewRequestN.current })
  }, [])
  const clearAppliedView = useCallback((n: number) => {
    setViewReq((current) => current?.n === n ? null : current)
  }, [])
  const rememberOrbitTarget = useCallback((event: any) => {
    if (event?.target?.target) orbitTarget.copy(event.target.target)
  }, [orbitTarget])
  const markCustomView = useCallback(() => setView(null), [])

  useEffect(() => {
    fitted.current = false
    setBox(null)
    setPicked(null)
  }, [partId])

  useEffect(() => {
    setDimensionDrafts({})
  }, [visibleFeatures])

  useEffect(() => {
    if (picked && !visibleFeatures.some((feature) => feature.feature_id === picked)) {
      setPicked(null)
    }
  }, [visibleFeatures, picked])

  useEffect(() => {
    if (!box || fitted.current) return
    fitted.current = true
    requestView("iso")
  }, [box, requestView])

  const clipPlane = useMemo(() => {
    if (!section || !box) return null
    const x = box.min.x + (box.max.x - box.min.x) * sectionT
    return new THREE.Plane(new THREE.Vector3(1, 0, 0), -x)
  }, [section, box, sectionT])

  async function commitDimension(field: DimensionField) {
    if (!selected) return
    const draftKey = `${selected.feature_id}:${field.key}`
    const raw = dimensionDrafts[draftKey]
    if (raw == null) return
    const value = Number(raw)
    if (!Number.isFinite(value) || value <= 0) {
      setDimensionDrafts((current) => {
        const next = { ...current }
        delete next[draftKey]
        return next
      })
      return
    }
    if (value === Number(field.value)) {
      setDimensionDrafts((current) => {
        const next = { ...current }
        delete next[draftKey]
        return next
      })
      return
    }
    await onPatchFeature({
      feature_overrides: [{
        feature_id: selected.feature_id,
        dimensions: { [field.key]: value },
      }],
    })
  }

  const shadow = useMemo(() => (box ? contactShadowFromBox(box) : null), [box])

  return (
    <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)_280px] xl:grid-cols-[240px_minmax(0,1fr)_300px]">
      <section className="rounded border border-[#e2e8f0] bg-[#f8fafc] p-3">
        <div className="mb-3 text-xs font-medium text-slate-700">特征树</div>
        <div className="max-h-[260px] space-y-1 overflow-auto text-sm lg:max-h-[420px]">
          {visibleFeatures.length ? visibleFeatures.map((f) => {
            const on = f.selected !== false
            const active = f.feature_id === picked
            return (
              <button
                type="button"
                key={f.feature_id}
                className={`flex w-full items-center justify-between gap-2 rounded border px-2 py-2 text-left ${active ? "border-blue-600 bg-blue-50 text-blue-800" : "border-[#e2e8f0] bg-white"}`}
                onClick={() => setPicked(f.feature_id)}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    className="accent-blue-600"
                    disabled={locked || busy}
                    checked={on}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => onToggle(f.feature_id, event.target.checked)}
                  />
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-xs">{f.feature_id}</span>
                    <span className="block truncate text-[11px] text-slate-500">{f.type || "特征"}</span>
                  </span>
                </span>
                {!on && <span className="shrink-0 text-[10px] text-slate-400">未选</span>}
              </button>
            )
          }) : <div className="text-xs text-slate-400">暂无特征</div>}
        </div>
      </section>

      <section className="relative h-[360px] w-full touch-none overflow-hidden rounded border border-[#e2e8f0] bg-[radial-gradient(circle_at_46%_38%,#ffffff_0%,#f5f7fa_48%,#e8edf3_100%)] lg:h-auto lg:min-h-[420px]">
        <div className="pointer-events-none absolute bottom-2 left-2 z-10 rounded bg-white/85 px-2 py-1 text-[10px] text-slate-500">
          3D 预览
        </div>
        {meshAvailable ? (
          <>
            <Canvas
              shadows
              camera={INITIAL_CAMERA}
              gl={CANVAS_GL}
              onPointerMissed={() => setPicked(null)}
            >
              <ambientLight color="#f8fafc" intensity={0.62} />
              <hemisphereLight args={["#ffffff", "#cbd5e1", 1.15]} />
              <directionalLight color="#fffdf8" position={[90, 140, 80]} intensity={1.25} />
              <directionalLight color="#dbeafe" position={[-70, 45, 35]} intensity={0.42} />
              <directionalLight color="#ffffff" position={[20, 55, -90]} intensity={0.32} />
              <Suspense fallback={null}>
                <CadBody
                  url={meshUrl}
                  clipPlane={clipPlane}
                  onBox={onBox}
                  onPick={pickSurface}
                />
                <group>
                  {pickables.map((f) => (
                    <FeatureMark
                      key={f.feature_id}
                      feat={f}
                      selected={f.feature_id === picked}
                      unitScale={featureUnitScale}
                    />
                  ))}
                </group>
                {section && box && <SectionHelper box={box} t={sectionT} />}
                {shadow && (
                  <ContactShadows
                    position={shadow.position}
                    opacity={0.48}
                    scale={shadow.scale}
                    blur={2}
                    far={shadow.far}
                    color="#334155"
                    resolution={1024}
                  />
                )}
              </Suspense>
              <OrbitControls
                makeDefault
                enablePan
                enableRotate
                enableZoom
                dampingFactor={0.08}
                enableDamping
                target={orbitTarget}
                onChange={rememberOrbitTarget}
                onEnd={markCustomView}
              />
              <ViewRig box={box} request={viewReq} onApplied={clearAppliedView} />
              <CadAxesGizmo />
            </Canvas>
            <ViewerToolbar
              view={view}
              section={section}
              sectionT={sectionT}
              onView={requestView}
              onSection={setSection}
              onSectionT={setSectionT}
            />
          </>
        ) : (
          <div className="flex h-full min-h-[360px] items-center justify-center px-6 text-sm text-slate-500">
            暂无模型。重新解析 STEP 后可审查，不展示假模型。
          </div>
        )}
      </section>

      <section className="rounded border border-[#e2e8f0] bg-[#f8fafc] p-3">
        <div className="mb-3 text-xs font-medium text-slate-700">特征详细参数</div>
        <div className="max-h-[520px] overflow-auto pr-1">
          {selected && fields ? (
            <div className="space-y-4">
              <div>
                <div className="mb-2 text-[11px] text-slate-500">物理参数</div>
                <dl className="grid grid-cols-[64px_1fr] items-center gap-y-2 text-xs">
                  <dt className="text-slate-500">id</dt>
                  <dd className="truncate font-mono" title={selected.feature_id}>{selected.feature_id}</dd>
                  <dt className="text-slate-500">类型</dt>
                  <dd>{selected.type || "—"}</dd>
                </dl>
                {!!dimensions.length && (
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {dimensions.map((field) => {
                      const draftKey = `${selected.feature_id}:${field.key}`
                      return <label key={field.key} className="text-xs text-slate-500">
                        <span>{field.label}</span>
                        <span className="mt-1 flex items-center rounded border border-[#e2e8f0] bg-white focus-within:border-blue-600">
                          {field.prefix && <span className="pl-2 text-slate-500">{field.prefix}</span>}
                          <input
                            type="number"
                            min="0.0001"
                            step="any"
                            className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm text-slate-900 outline-none disabled:bg-[#f8fafc]"
                            disabled={locked || busy}
                            value={dimensionDrafts[draftKey] ?? displayValue(field.value).replace("—", "")}
                            onChange={(event) => setDimensionDrafts((current) => ({
                              ...current,
                              [draftKey]: event.target.value,
                            }))}
                            onBlur={() => commitDimension(field)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") event.currentTarget.blur()
                            }}
                          />
                          <span className="pr-2 text-[10px] text-slate-400">mm</span>
                        </span>
                      </label>
                    })}
                  </div>
                )}
                {(featType(selected) === "hole" || featType(selected) === "thread") && (
                  <dl className="mt-3 grid grid-cols-[64px_1fr] gap-y-2 text-xs">
                    <dt className="text-slate-500">通盲</dt>
                    <dd>{holeLabel(selected.hole_type)}</dd>
                    <dt className="text-slate-500">方位</dt>
                    <dd>{displayValue(fields.orient)}</dd>
                  </dl>
                )}
                {featType(selected) === "surface" && (
                  <dl className="mt-3 grid grid-cols-[64px_1fr] gap-y-2 text-xs">
                    <dt className="text-slate-500">R</dt>
                    <dd>{fields.r != null ? `${fields.r} mm` : "—"}</dd>
                  </dl>
                )}
              </div>

              <div className="border-t border-[#e2e8f0] pt-3">
                <div className="mb-2 text-[11px] text-slate-500">加工参数</div>
                {selectedSteps.length ? (
                  <div className="space-y-3">
                    {selectedSteps.map((step) => (
                      <div key={step.step_id} className="rounded border border-[#e2e8f0] bg-white p-2">
                        <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                          <span className="truncate font-medium">{processName(step)}</span>
                          <span className="shrink-0 text-slate-400">STEP {step.order || "—"}</span>
                        </div>
                        <ProcessStepParameters
                          step={step}
                          locked={locked}
                          busy={busy}
                          onPatch={onPatchProcess}
                          showFormula={false}
                          compact
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-400">该特征暂无匹配工序</div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex min-h-32 items-center justify-center text-center text-xs text-slate-400">
              请从特征树或 3D 模型中选择特征
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
