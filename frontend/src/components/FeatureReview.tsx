import { Suspense, useEffect, useMemo, useState } from "react"
import { Canvas } from "@react-three/fiber"
import { OrbitControls } from "@react-three/drei"
import * as THREE from "three"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"
import { API } from "../api"

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

function Body({ url }: { url: string }) {
  const scene = useGltfScene(url)
  if (!scene) return null
  return <primitive object={scene} />
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

function FeatureMark({
  feat, selected, onPick,
}: { feat: Feat; selected: boolean; onPick: (id: string) => void }) {
  const pose = poseOf(feat)
  if (!pose) return null
  const pick = (e: any) => { e.stopPropagation(); onPick(feat.feature_id) }

  if (pose.kind === "cyl") {
    const mid = pose.centered
      ? pose.origin
      : pose.origin.clone().add(pose.axis.clone().multiplyScalar(pose.length / 2))
    return (
      <mesh position={mid} quaternion={quatFromAxis(pose.axis)} onClick={pick}>
        <cylinderGeometry args={[pose.diameter / 2, pose.diameter / 2, pose.length, 24]} />
        <MarkMaterial selected={selected} opacity={selected ? 0.55 : 0.18} />
      </mesh>
    )
  }

  if (pose.kind === "plate" || pose.kind === "box") {
    return (
      <mesh position={pose.origin} quaternion={quatFromAxis(pose.axis)} onClick={pick}>
        <boxGeometry args={pose.size} />
        <MarkMaterial selected={selected} opacity={selected ? 0.45 : 0.16} />
      </mesh>
    )
  }

  const hintR = Math.min(pose.radius, 16)
  return (
    <group position={pose.origin} onClick={pick}>
      <mesh>
        <boxGeometry args={[8, 8, 8]} />
        <MarkMaterial selected={selected} opacity={selected ? 0.5 : 0.2} />
      </mesh>
      <mesh>
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
  const meshUrl = `${API}/parts/${partId}/mesh`
  const selected = features.find((f) => f.feature_id === picked)
  const pickables = useMemo(() => features.filter((f) => poseOf(f)), [features])
  const fields = selected ? inspectorFields(selected) : null

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <div className="h-[320px] w-full touch-none rounded border border-[#e2e8f0] bg-[#f8fafc] md:h-auto md:min-h-[320px]">
        {meshAvailable ? (
          <Canvas camera={{ position: [80, 60, 80], fov: 45 }} onPointerMissed={() => setPicked(null)}>
            <ambientLight intensity={0.7} />
            <directionalLight position={[80, 120, 60]} intensity={0.9} />
            <Suspense fallback={null}>
              <Body url={meshUrl} />
              {pickables.map((f) => (
                <FeatureMark
                  key={f.feature_id}
                  feat={f}
                  selected={f.feature_id === picked}
                  onPick={setPicked}
                />
              ))}
            </Suspense>
            <OrbitControls makeDefault enablePan enableRotate enableZoom />
          </Canvas>
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
