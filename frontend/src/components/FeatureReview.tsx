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
import { disableRaycast, pickBestFeature } from "./featureReviewPick"
import { applyView, contactShadowFromBox, type ViewName } from "./featureReviewView"

type Feat = any

type Pose =
  | { kind: "cyl"; origin: THREE.Vector3; axis: THREE.Vector3; length: number; diameter: number; centered: boolean }
  | { kind: "plate"; origin: THREE.Vector3; axis: THREE.Vector3; size: [number, number, number] }
  | { kind: "box"; origin: THREE.Vector3; axis: THREE.Vector3; size: [number, number, number] }
  | { kind: "surface"; origin: THREE.Vector3; radius: number }

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

  if (t === "hole" || t === "thread") {
    if (!origin) return null
    const diameter = num(f.pose?.diameter_mm, f.diameter_mm, f.nominal_d, dim.diameter_mm) || 1
    const length = num(f.pose?.length_mm, f.depth_mm, f.thread_length, dim.thread_length, dim.depth_mm) || 1
    return { kind: "cyl", origin, axis, length, diameter, centered: !f.pose?.origin }
  }

  if (t === "face") {
    if (!origin) return null
    const L = num(f.length, dim.length) || 8
    const W = num(f.width, dim.width) || 8
    return { kind: "plate", origin, axis, size: [L, 1.2, W] }
  }

  if (t === "pocket" || t === "slot") {
    if (!origin) return null
    const L = num(f.length, dim.length) || 8
    const W = num(f.width, dim.width) || 8
    const H = num(f.depth, dim.depth, f.height, dim.height) || 4
    return { kind: "box", origin, axis, size: [L, H, W] }
  }

  if (t === "step") {
    if (!origin) return null
    const L = num(f.length, dim.length) || 8
    const W = num(f.width, dim.width) || 8
    const H = num(f.height, dim.height, f.depth, dim.depth) || 4
    return { kind: "box", origin, axis, size: [L, H, W] }
  }

  if (t === "surface") {
    if (!origin) return null
    const radius = num(f.curvature_radius, dim.curvature_radius, f.radius_mm, f.radius, f.R, dim.R) || 8
    return { kind: "surface", origin, radius }
  }

  return null
}

function quatFromAxis(axis: THREE.Vector3) {
  const q = new THREE.Quaternion()
  q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis)
  return q
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

function ViewRig({ box, request }: { box: THREE.Box3 | null; request: { view: ViewName; n: number } }) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera
  const controls = useThree((s) => s.controls)
  const size = useThree((s) => s.size)
  useLayoutEffect(() => {
    if (!box || !request.n) return
    if (size.width > 0 && size.height > 0) camera.aspect = size.width / size.height
    applyView(camera, controls, box, request.view)
  }, [box, request, camera, controls, size])
  return null
}

function CadAxesGizmo() {
  const root = useRef<THREE.Group>(null)
  useLayoutEffect(() => {
    let node: THREE.Object3D | null = root.current
    while (node?.parent) node = node.parent
    disableRaycast(node)
  })
  return (
    <GizmoHelper alignment="top-right" margin={[64, 64]} renderPriority={1}>
      <group ref={root} raycast={() => null}>
        <GizmoViewport
          disabled
          axisColors={["#ef4444", "#22c55e", "#3b82f6"]}
          labelColor="#ffffff"
          axisHeadScale={0.82}
          hideNegativeAxes
        />
      </group>
    </GizmoHelper>
  )
}

function ContactShadowFloor(props: React.ComponentProps<typeof ContactShadows>) {
  const root = useRef<THREE.Group>(null)
  useLayoutEffect(() => {
    disableRaycast(root.current)
  })
  return <ContactShadows ref={root} {...props} />
}

function FeaturePickRoot({
  onPick,
  onMiss,
  children,
}: {
  onPick: (id: string) => void
  onMiss: () => void
  children: React.ReactNode
}) {
  const group = useRef<THREE.Group>(null)
  const camera = useThree((state) => state.camera)
  const gl = useThree((state) => state.gl)
  const picker = useMemo(() => new THREE.Raycaster(), [])

  useEffect(() => {
    const el = gl.domElement
    const drag = { x: 0, y: 0, moved: false, onCanvas: false }
    const ndc = new THREE.Vector2()
    const down = (event: PointerEvent) => {
      drag.x = event.clientX
      drag.y = event.clientY
      drag.moved = false
      drag.onCanvas = true
    }
    const move = (event: PointerEvent) => {
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 5) drag.moved = true
    }
    const up = (event: PointerEvent) => {
      if (!drag.onCanvas) return
      drag.onCanvas = false
      if (event.button !== 0 || drag.moved) return
      const rect = el.getBoundingClientRect()
      if (rect.width < 1 || rect.height < 1) return
      ndc.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      )
      picker.setFromCamera(ndc, camera)
      const id = group.current ? pickBestFeature(picker.intersectObject(group.current, true)) : null
      if (id) onPick(id)
      else onMiss()
    }
    el.addEventListener("pointerdown", down)
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up)
    return () => {
      el.removeEventListener("pointerdown", down)
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
    }
  }, [camera, gl, onMiss, onPick, picker])

  return (
    <group
      ref={group}
      onClick={(event) => {
        event.stopPropagation()
        const id = pickBestFeature(event.intersections)
        if (id) onPick(id)
      }}
    >
      {children}
    </group>
  )
}

function CadBody({
  url, clipPlane, onBox,
}: {
  url: string
  clipPlane: THREE.Plane | null
  onBox: (box: THREE.Box3) => void
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
  return <primitive object={root} />
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

function pickRank(kind: Pose["kind"]) {
  if (kind === "cyl") return 0
  if (kind === "box") return 1
  if (kind === "surface") return 2
  return 3
}

function FeatureMark({ feat, selected }: { feat: Feat; selected: boolean }) {
  const pose = poseOf(feat)
  if (!pose) return null
  const rank = pickRank(pose.kind)
  const data = { featureId: feat.feature_id, pickRank: rank }
  const order = 3 - rank
  const q = pose.kind === "surface" ? undefined : quatFromAxis(pose.axis)
  const mid = pose.kind === "cyl"
    ? (pose.centered ? pose.origin : pose.origin.clone().add(pose.axis.clone().multiplyScalar(pose.length / 2)))
    : pose.kind === "surface" ? pose.origin : pose.origin

  let geo = null
  if (pose.kind === "cyl") geo = <cylinderGeometry args={[pose.diameter / 2, pose.diameter / 2, pose.length, 24]} />
  else if (pose.kind === "plate" || pose.kind === "box") geo = <boxGeometry args={pose.size} />
  else geo = <boxGeometry args={[8, 8, 8]} />

  return (
    <group position={mid} quaternion={q} userData={data}>
      <mesh userData={data} renderOrder={order}>
        {geo}
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {selected && (
        <lineSegments renderOrder={8} raycast={() => {}}>
          {pose.kind === "cyl" && <edgesGeometry args={[new THREE.CylinderGeometry(pose.diameter / 2, pose.diameter / 2, pose.length, 24), 20]} />}
          {(pose.kind === "plate" || pose.kind === "box") && <edgesGeometry args={[new THREE.BoxGeometry(...pose.size), 15]} />}
          {pose.kind === "surface" && <edgesGeometry args={[new THREE.SphereGeometry(Math.min(pose.radius, 16), 16, 12), 15]} />}
          <lineBasicMaterial color="#2563eb" />
        </lineSegments>
      )}
    </group>
  )
}

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
  view: ViewName
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
  const [view, setView] = useState<ViewName>("iso")
  const [viewReq, setViewReq] = useState({ view: "iso" as ViewName, n: 0 })
  const [section, setSection] = useState(false)
  const [sectionT, setSectionT] = useState(0.5)
  const fitted = useRef(false)
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
  const fields = selected ? inspectorFields(selected) : null
  const dimensions = selected ? editableDimensions(selected) : []
  const selectedSteps = useMemo(
    () => processSequence.filter((step) => step.feature_id === picked),
    [processSequence, picked],
  )
  const onBox = useCallback((b: THREE.Box3) => setBox(b.clone()), [])

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
    setView("iso")
    setViewReq((s) => ({ view: "iso", n: s.n + 1 }))
  }, [box])

  const clipPlane = useMemo(() => {
    if (!section || !box) return null
    const x = box.min.x + (box.max.x - box.min.x) * sectionT
    return new THREE.Plane(new THREE.Vector3(1, 0, 0), -x)
  }, [section, box, sectionT])

  const requestView = (v: ViewName) => {
    setView(v)
    setViewReq((s) => ({ view: v, n: s.n + 1 }))
  }

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
  const pickFeature = useCallback((id: string) => setPicked(id), [])
  const clearPick = useCallback(() => setPicked(null), [])

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
              camera={{ position: [72, 48, 62], fov: 42, near: 0.1, far: 4000 }}
              gl={{ antialias: true, alpha: true, localClippingEnabled: true }}
            >
              <ambientLight color="#f8fafc" intensity={0.62} />
              <hemisphereLight args={["#ffffff", "#cbd5e1", 1.15]} />
              <directionalLight color="#fffdf8" position={[90, 140, 80]} intensity={1.25} />
              <directionalLight color="#dbeafe" position={[-70, 45, 35]} intensity={0.42} />
              <directionalLight color="#ffffff" position={[20, 55, -90]} intensity={0.32} />
              <Suspense fallback={null}>
                <CadBody url={meshUrl} clipPlane={clipPlane} onBox={onBox} />
                <FeaturePickRoot onPick={pickFeature} onMiss={clearPick}>
                  {pickables.map((f) => (
                    <FeatureMark
                      key={f.feature_id}
                      feat={f}
                      selected={f.feature_id === picked}
                    />
                  ))}
                </FeaturePickRoot>
                {section && box && <SectionHelper box={box} t={sectionT} />}
                {shadow && (
                  <ContactShadowFloor
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
              />
              <ViewRig box={box} request={viewReq} />
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
