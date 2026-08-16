import { Suspense, useMemo, useState } from "react"
import { Canvas } from "@react-three/fiber"
import { OrbitControls, useGLTF } from "@react-three/drei"
import * as THREE from "three"
import { API } from "../api"

type Feat = any

function holeLabel(ht: string | undefined) {
  if (ht === "through" || ht === "通孔") return "通孔"
  if (ht === "blind" || ht === "盲孔") return "盲孔"
  return ht || "—"
}

function poseOf(f: Feat) {
  const pose = f.pose
  if (pose?.origin && pose?.axis && pose.diameter_mm) {
    return {
      origin: new THREE.Vector3(pose.origin.x, pose.origin.y, pose.origin.z),
      axis: new THREE.Vector3(pose.axis.x, pose.axis.y, pose.axis.z).normalize(),
      length: Number(pose.length_mm || f.depth_mm || 1),
      diameter: Number(pose.diameter_mm || f.diameter_mm || 1),
    }
  }
  const loc = f.location
  const ax = f.axis
  if (loc && ax && f.diameter_mm) {
    return {
      origin: new THREE.Vector3(loc.x, loc.y, loc.z),
      axis: new THREE.Vector3(ax.x, ax.y, ax.z).normalize(),
      length: Number(f.depth_mm || 1),
      diameter: Number(f.diameter_mm),
    }
  }
  return null
}

function quatFromAxis(axis: THREE.Vector3) {
  const q = new THREE.Quaternion()
  q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis)
  return q
}

function Body({ url }: { url: string }) {
  const gltf = useGLTF(url)
  return <primitive object={gltf.scene} />
}

function FeatureMark({
  feat, selected, onPick,
}: { feat: Feat; selected: boolean; onPick: (id: string) => void }) {
  const pose = poseOf(feat)
  if (!pose) return null
  const mid = pose.origin.clone().add(pose.axis.clone().multiplyScalar(pose.length / 2))
  return (
    <mesh
      position={mid}
      quaternion={quatFromAxis(pose.axis)}
      onClick={(e) => { e.stopPropagation(); onPick(feat.feature_id) }}
    >
      <cylinderGeometry args={[pose.diameter / 2, pose.diameter / 2, pose.length, 24]} />
      <meshStandardMaterial
        color={selected ? "#2563eb" : "#38bdf8"}
        transparent
        opacity={selected ? 0.55 : 0.18}
        depthWrite={false}
      />
    </mesh>
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
  const meshUrl = `${API}/parts/${partId}/mesh`
  const selected = features.find((f) => f.feature_id === picked)
  const pickables = useMemo(() => features.filter((f) => poseOf(f)), [features])

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <div className="min-h-[320px] rounded border border-[#e2e8f0] bg-[#f8fafc]">
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
          {selected ? (
            <dl className="grid grid-cols-[72px_1fr] gap-y-1 text-xs">
              <dt className="text-slate-500">id</dt><dd>{selected.feature_id}</dd>
              <dt className="text-slate-500">类型</dt><dd>{selected.type || "—"}</dd>
              <dt className="text-slate-500">D</dt><dd>{selected.diameter_mm != null ? `Ø${selected.diameter_mm}` : "—"}</dd>
              <dt className="text-slate-500">H</dt><dd>{selected.depth_mm != null ? selected.depth_mm : "—"}</dd>
              <dt className="text-slate-500">通盲</dt><dd>{holeLabel(selected.hole_type)}</dd>
              <dt className="text-slate-500">方位</dt><dd>{selected.position_type || "—"}</dd>
            </dl>
          ) : (
            <div className="text-xs text-slate-400">点列表或模型上的特征</div>
          )}
        </div>
      </div>
    </div>
  )
}
