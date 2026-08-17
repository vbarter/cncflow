import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Canvas, useThree } from "@react-three/fiber"
import { ContactShadows, OrbitControls } from "@react-three/drei"
import * as THREE from "three"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"
import { API } from "../api"

type Feat = any
type ViewName = "fit" | "front" | "top" | "side" | "iso"

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
    const radius = num(dim.curvature_radius, f.radius_mm, f.R, dim.R) || 8
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

function applyView(camera: THREE.PerspectiveCamera, controls: any, box: THREE.Box3, view: ViewName) {
  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const maxDim = Math.max(size.x, size.y, size.z, 1)
  const fov = (camera.fov * Math.PI) / 180
  const dist = ((maxDim / 2) / Math.tan(fov / 2)) * 1.4
  let dir: THREE.Vector3
  if (view === "fit") {
    dir = camera.position.clone().sub(controls?.target || center)
    if (dir.lengthSq() < 1e-8) dir.set(1, 0.85, 1)
    dir.normalize()
  } else if (view === "front") dir = new THREE.Vector3(0, 0, 1)
  else if (view === "top") dir = new THREE.Vector3(0, 1, 0)
  else if (view === "side") dir = new THREE.Vector3(1, 0, 0)
  else dir = new THREE.Vector3(1, 0.85, 1).normalize()

  camera.up.set(0, 1, 0)
  if (view === "top") camera.up.set(0, 0, -1)
  camera.position.copy(center).add(dir.multiplyScalar(dist))
  camera.near = Math.max(dist / 120, 0.05)
  camera.far = Math.max(dist * 24, 2000)
  camera.updateProjectionMatrix()
  if (controls) {
    controls.target.copy(center)
    controls.update()
  }
}

function ViewRig({ box, request }: { box: THREE.Box3 | null; request: { view: ViewName; n: number } }) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera
  const controls = useThree((s) => s.controls)
  useEffect(() => {
    if (!box || !request.n) return
    applyView(camera, controls, box, request.view)
  }, [box, request, camera, controls])
  return null
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
        color: 0xb7c2cc,
        metalness: 0.16,
        roughness: 0.4,
        side: THREE.DoubleSide,
      })
      const edges = new THREE.EdgesGeometry(o.geometry, 22)
      const lines = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({ color: 0x1e293b, transparent: true, opacity: 0.88 }),
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

function MarkMaterial({ selected, opacity }: { selected: boolean; opacity: number }) {
  return (
    <meshStandardMaterial
      color={selected ? "#2563eb" : "#38bdf8"}
      transparent
      opacity={opacity}
      depthWrite={false}
    />
  )
}

function pickRank(kind: Pose["kind"]) {
  if (kind === "cyl") return 0
  if (kind === "box") return 1
  if (kind === "surface") return 2
  return 3
}

function pickBestFeature(intersections: any[]): string | null {
  let best: { id: string; rank: number; dist: number } | null = null
  for (const hit of intersections || []) {
    let o = hit.object as THREE.Object3D | null
    while (o) {
      const id = o.userData?.featureId
      if (id) {
        const rank = Number(o.userData.pickRank ?? 9)
        if (!best || rank < best.rank || (rank === best.rank && hit.distance < best.dist)) {
          best = { id, rank, dist: hit.distance }
        }
        break
      }
      o = o.parent
    }
  }
  return best?.id || null
}

function FeatureMark({ feat, selected }: { feat: Feat; selected: boolean }) {
  const pose = poseOf(feat)
  if (!pose) return null
  const rank = pickRank(pose.kind)
  const data = { featureId: feat.feature_id, pickRank: rank }
  const order = 3 - rank

  if (pose.kind === "cyl") {
    const mid = pose.centered
      ? pose.origin
      : pose.origin.clone().add(pose.axis.clone().multiplyScalar(pose.length / 2))
    return (
      <mesh position={mid} quaternion={quatFromAxis(pose.axis)} userData={data} renderOrder={order}>
        <cylinderGeometry args={[pose.diameter / 2, pose.diameter / 2, pose.length, 24]} />
        <MarkMaterial selected={selected} opacity={selected ? 0.55 : 0.18} />
      </mesh>
    )
  }

  if (pose.kind === "plate" || pose.kind === "box") {
    return (
      <mesh position={pose.origin} quaternion={quatFromAxis(pose.axis)} userData={data} renderOrder={order}>
        <boxGeometry args={pose.size} />
        <MarkMaterial selected={selected} opacity={selected ? 0.45 : 0.16} />
      </mesh>
    )
  }

  const hintR = Math.min(pose.radius, 16)
  return (
    <group position={pose.origin} userData={data} renderOrder={order}>
      <mesh userData={data} renderOrder={order}>
        <boxGeometry args={[8, 8, 8]} />
        <MarkMaterial selected={selected} opacity={selected ? 0.5 : 0.2} />
      </mesh>
      <mesh userData={data} renderOrder={order} raycast={() => {}}>
        <sphereGeometry args={[hintR, 16, 12]} />
        <meshStandardMaterial
          color={selected ? "#2563eb" : "#38bdf8"}
          wireframe
          transparent
          opacity={selected ? 0.55 : 0.22}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

function inspectorFields(f: Feat) {
  const dim = f.dimensions || {}
  return {
    d: f.diameter_mm ?? f.nominal_d ?? dim.diameter_mm,
    h: f.depth_mm ?? f.thread_length ?? dim.thread_length ?? dim.depth ?? dim.height ?? f.height,
    r: dim.curvature_radius ?? f.radius_mm ?? f.R ?? dim.R,
    orient: f.position_type || f.face_position || dim.face_position || f.position || dim.position,
  }
}

function ViewerToolbar({
  view, section, sectionT, onView, onSection, onSectionT,
}: {
  view: ViewName
  section: boolean
  sectionT: number
  onView: (v: ViewName) => void
  onSection: (on: boolean) => void
  onSectionT: (t: number) => void
}) {
  const btn = (id: ViewName, label: string) => (
    <button
      type="button"
      className={`h-7 rounded border px-2 text-[11px] ${view === id ? "border-blue-600 bg-blue-50 text-blue-700" : "border-[#e2e8f0] bg-white text-slate-700"}`}
      onClick={() => onView(id)}
    >
      {label}
    </button>
  )
  return (
    <div
      className="absolute left-2 top-2 z-10 flex flex-wrap items-center gap-1"
      onPointerDown={(e) => e.stopPropagation()}
    >
      {btn("fit", "适应")}
      {btn("front", "前")}
      {btn("top", "顶")}
      {btn("side", "侧")}
      {btn("iso", "ISO")}
      <button
        type="button"
        className={`h-7 rounded border px-2 text-[11px] ${section ? "border-blue-600 bg-blue-50 text-blue-700" : "border-[#e2e8f0] bg-white text-slate-700"}`}
        onClick={() => onSection(!section)}
      >
        剖切
      </button>
      {section && (
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(sectionT * 100)}
          onChange={(e) => onSectionT(Number(e.target.value) / 100)}
          className="h-7 w-20 accent-blue-600"
          aria-label="剖切位置"
        />
      )}
    </div>
  )
}

export function FeatureReview({
  partId, features, meshAvailable, locked, busy, onToggle,
}: {
  partId: string
  features: Feat[]
  meshAvailable: boolean
  locked: boolean
  busy: boolean
  onToggle: (id: string, checked: boolean) => void
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const [box, setBox] = useState<THREE.Box3 | null>(null)
  const [view, setView] = useState<ViewName>("iso")
  const [viewReq, setViewReq] = useState({ view: "iso" as ViewName, n: 0 })
  const [section, setSection] = useState(false)
  const [sectionT, setSectionT] = useState(0.5)
  const fitted = useRef(false)
  const meshUrl = `${API}/parts/${partId}/mesh`
  const selected = features.find((f) => f.feature_id === picked)
  const pickables = useMemo(() => features.filter((f) => poseOf(f)), [features])
  const fields = selected ? inspectorFields(selected) : null
  const onBox = useCallback((b: THREE.Box3) => setBox(b.clone()), [])

  useEffect(() => {
    fitted.current = false
    setBox(null)
  }, [partId])

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

  const shadow = useMemo(() => {
    if (!box) return null
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    return {
      position: [center.x, box.min.y - 0.15, center.z] as [number, number, number],
      scale: Math.max(size.x, size.z, 1) * 2.2,
    }
  }, [box])

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <div className="relative h-[320px] w-full touch-none rounded border border-[#e2e8f0] bg-[#f8fafc] md:h-auto md:min-h-[320px]">
        {meshAvailable ? (
          <>
            <Canvas
              shadows
              camera={{ position: [80, 60, 80], fov: 45, near: 0.1, far: 4000 }}
              gl={{ antialias: true, localClippingEnabled: true }}
              onPointerMissed={() => setPicked(null)}
            >
              <hemisphereLight args={["#f8fafc", "#94a3b8", 0.62]} />
              <ambientLight intensity={0.28} />
              <directionalLight position={[90, 140, 70]} intensity={1.05} />
              <Suspense fallback={null}>
                <CadBody url={meshUrl} clipPlane={clipPlane} onBox={onBox} />
                <group
                  onClick={(e) => {
                    e.stopPropagation()
                    const id = pickBestFeature(e.intersections)
                    if (id) setPicked(id)
                  }}
                >
                  {pickables.map((f) => (
                    <FeatureMark
                      key={f.feature_id}
                      feat={f}
                      selected={f.feature_id === picked}
                    />
                  ))}
                </group>
                {section && box && <SectionHelper box={box} t={sectionT} />}
                {shadow && (
                  <ContactShadows
                    position={shadow.position}
                    opacity={0.28}
                    scale={shadow.scale}
                    blur={2.4}
                    far={40}
                  />
                )}
              </Suspense>
              <OrbitControls makeDefault enablePan enableRotate enableZoom />
              <ViewRig box={box} request={viewReq} />
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
          <div className="flex h-[320px] items-center justify-center px-6 text-sm text-slate-500">
            暂无模型。重新解析 STEP 后可审查，不展示假模型。
          </div>
        )}
      </div>
      <div className="space-y-3">
        <div className="text-xs text-slate-500">特征列表 · 点选对打</div>
        <div className="max-h-[220px] space-y-1 overflow-auto text-sm">
          {features.length ? features.map((f) => {
            const on = f.selected !== false
            const active = f.feature_id === picked
            return (
              <button
                type="button"
                key={f.feature_id}
                className={`flex w-full items-center justify-between gap-2 rounded border px-2 py-1.5 text-left ${active ? "border-blue-600 bg-blue-50" : "border-[#e2e8f0]"}`}
                onClick={() => setPicked(f.feature_id)}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    disabled={locked || busy}
                    checked={on}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => onToggle(f.feature_id, e.target.checked)}
                  />
                  <span className="truncate">{f.feature_id} · {f.type || "特征"}</span>
                </span>
                <span className="shrink-0 text-xs text-slate-500">{on ? "" : "未选"}</span>
              </button>
            )
          }) : <div className="text-slate-400">暂无特征</div>}
        </div>
        <div className="rounded border border-[#e2e8f0] bg-white p-3 text-sm">
          <div className="mb-2 text-xs text-slate-500">Inspector</div>
          {selected && fields ? (
            <dl className="grid grid-cols-[72px_1fr] gap-y-1 text-xs">
              <dt className="text-slate-500">id</dt><dd>{selected.feature_id}</dd>
              <dt className="text-slate-500">类型</dt><dd>{selected.type || "—"}</dd>
              <dt className="text-slate-500">D</dt><dd>{fields.d != null ? `Ø${fields.d}` : "—"}</dd>
              <dt className="text-slate-500">H</dt><dd>{fields.h != null ? fields.h : "—"}</dd>
              <dt className="text-slate-500">R</dt><dd>{fields.r != null ? fields.r : "—"}</dd>
              <dt className="text-slate-500">通盲</dt><dd>{holeLabel(selected.hole_type)}</dd>
              <dt className="text-slate-500">方位</dt><dd>{fields.orient || "—"}</dd>
            </dl>
          ) : (
            <div className="text-xs text-slate-400">点列表或模型上的特征</div>
          )}
        </div>
      </div>
    </div>
  )
}
