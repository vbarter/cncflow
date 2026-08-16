import { useRef, useState } from "react"
import { UploadCloud } from "lucide-react"
import { Button, Card, Input, Select } from "../components/ui"
import { json, upload } from "../api"

type PartDraft = {
  name: string
  qty: string
  material: string
  surface_finish: string
  precision: string
  roughness_ra: string
  step?: File
  pdf?: File
}

const empty = (): PartDraft => ({
  name: "", qty: "1", material: "AL6061-T6", surface_finish: "无",
  precision: "普通(ISO 2768-m)", roughness_ra: "3.2",
})

function isStep(f: File) {
  const n = f.name.toLowerCase()
  return n.endsWith(".step") || n.endsWith(".stp")
}
function isPdf(f: File) { return f.name.toLowerCase().endsWith(".pdf") }
function stem(f: File) { return f.name.replace(/\.[^.]+$/, "") }

export function NewInquiry({ go }: { go: (h: string) => void }) {
  const [customer, setCustomer] = useState("")
  const [rfq, setRfq] = useState("")
  const [project, setProject] = useState("")
  const [due, setDue] = useState("")
  const [parts, setParts] = useState<PartDraft[]>([empty()])
  const [err, setErr] = useState("")
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)
  const stepRef = useRef<HTMLInputElement>(null)
  const pdfRef = useRef<HTMLInputElement>(null)
  const dropRef = useRef<HTMLInputElement>(null)
  const fileRow = useRef<{ i: number; kind: "step" | "pdf" } | null>(null)

  function upd(i: number, patch: Partial<PartDraft>) {
    setParts(p => p.map((x, idx) => idx === i ? { ...x, ...patch } : x))
  }
  function addFiles(list: FileList | File[]) {
    const files = Array.from(list)
    setParts(prev => {
      const next = [...prev]
      for (const f of files) {
        if (isStep(f)) {
          const slot = next.findIndex(p => !p.step && !p.name)
          if (slot >= 0) next[slot] = { ...next[slot], name: next[slot].name || stem(f), step: f }
          else next.push({ ...empty(), name: stem(f), step: f })
        } else if (isPdf(f)) {
          const slot = [...next].reverse().findIndex(p => !p.pdf)
          const idx = slot >= 0 ? next.length - 1 - slot : -1
          if (idx >= 0) next[idx] = { ...next[idx], pdf: f, name: next[idx].name || stem(f) }
          else next.push({ ...empty(), name: stem(f), pdf: f })
        }
      }
      return next.length ? next : [empty()]
    })
  }
  async function submit() {
    const usable = parts.filter(p => p.name.trim() || p.step)
    if (!usable.length) { setErr("请至少添加一个零件名称或 STEP 图纸"); return }
    setErr(""); setBusy(true)
    try {
      const inq = await json<any>("/inquiries", {
        method: "POST",
        body: JSON.stringify({ customer, project, due_date: due, title: project || rfq }),
      })
      for (const p of usable) {
        await json(`/inquiries/${inq.id}/parts`, {
          method: "POST",
          body: JSON.stringify({
            name: p.name || (p.step ? stem(p.step) : "零件"),
            qty: Number(p.qty) || 1,
            material: p.material,
            blank_type: "板料",
            length: 80, width: 60, height: 20,
            surface_finish: p.surface_finish === "无" ? "" : p.surface_finish,
            tolerance_it: p.precision.includes("精密") ? 7 : 11,
            roughness_ra: Number(p.roughness_ra) || 3.2,
            batch_size: Number(p.qty) || 1,
          }),
        })
        if (p.step || p.pdf) {
          const form = new FormData()
          if (p.step) form.append("step_file", p.step)
          if (p.pdf) form.append("drawing_file", p.pdf)
          await upload("/parse-jobs", form)
        }
      }
      go("parsing/" + inq.id)
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  return <div className="space-y-6">
    <button type="button" className="text-sm text-blue-600" onClick={() => go("")}>← 返回报价工作台</button>
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-500">CREATE RFQ / STEP 01</div>
      <h1 className="font-serif mt-2 text-3xl font-semibold tracking-tight text-slate-900">新建报价</h1>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">提交基本信息与多个零件图纸，AI 将据此生成可审核的加工方案。</p>
    </div>

    <Card className="p-5">
      <div className="mb-4 text-sm font-medium text-slate-800">01. 询价基本信息</div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-xs text-slate-500">客户<Input className="mt-1" value={customer} onChange={e => setCustomer(e.target.value)} placeholder="输入客户名称" /></label>
        <label className="text-xs text-slate-500">询价单号<Input className="mt-1" value={rfq} onChange={e => setRfq(e.target.value)} placeholder="可选" /></label>
        <label className="text-xs text-slate-500">项目名称<Input className="mt-1" value={project} onChange={e => setProject(e.target.value)} placeholder="可选" /></label>
        <label className="text-xs text-slate-500">交期要求<Input className="mt-1" value={due} onChange={e => setDue(e.target.value)} placeholder="5 天" /></label>
      </div>
    </Card>

    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="text-sm font-medium text-slate-800">02. 零件列表</div>
        <button type="button" className="text-xs font-medium text-blue-600 hover:underline" onClick={() => setParts(p => [...p, empty()])}>+ 添加零件</button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead><tr className="border-b border-[#e2e8f0] bg-slate-50 text-xs text-slate-500">
            <th className="py-2 pr-2 font-normal">零件名称</th><th className="font-normal">数量</th><th className="font-normal">材料</th><th className="font-normal">表面处理</th><th className="font-normal">关键精度</th><th className="font-normal">粗糙度</th><th className="font-normal">图纸</th><th className="font-normal">状态</th><th className="font-normal">操作</th>
          </tr></thead>
          <tbody>
            {parts.map((p, i) => (
              <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 pr-2"><Input value={p.name} onChange={e => upd(i, { name: e.target.value })} /></td>
                <td className="w-20"><Input type="number" min={1} value={p.qty} onChange={e => upd(i, { qty: e.target.value })} /></td>
                <td><Select value={p.material} onChange={e => upd(i, { material: e.target.value })}>
                  <option>AL6061-T6</option><option>SUS304</option><option>AL7075</option><option>POM</option><option>铝合金</option><option>钢</option><option>不锈钢</option>
                </Select></td>
                <td><Select value={p.surface_finish} onChange={e => upd(i, { surface_finish: e.target.value })}>
                  <option>无</option><option>阳极氧化</option><option>镀锌</option>
                </Select></td>
                <td><Select value={p.precision} onChange={e => upd(i, { precision: e.target.value })}>
                  <option>普通(ISO 2768-m)</option><option>精密</option>
                </Select></td>
                <td><Select value={p.roughness_ra} onChange={e => upd(i, { roughness_ra: e.target.value })}>
                  <option value="3.2">Ra3.2</option><option value="1.6">Ra1.6</option><option value="0.8">Ra0.8</option>
                </Select></td>
                <td className="whitespace-nowrap">
                  <button type="button" className="mr-2 text-xs text-slate-500 hover:underline" onClick={() => { fileRow.current = { i, kind: "step" }; stepRef.current?.click() }}>{p.step ? p.step.name : "⇪ STEP"}</button>
                  <button type="button" className="text-xs text-slate-500 hover:underline" onClick={() => { fileRow.current = { i, kind: "pdf" }; pdfRef.current?.click() }}>{p.pdf ? p.pdf.name : "⇪ PDF"}</button>
                </td>
                <td><span className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-400">待分析</span></td>
                <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setParts(ps => ps.filter((_, idx) => idx !== i))}>删除</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <input ref={stepRef} type="file" accept=".step,.stp" className="hidden" onChange={e => { const f = e.target.files?.[0]; const row = fileRow.current; if (f && row) upd(row.i, { step: f, name: parts[row.i]?.name || stem(f) }); e.target.value = "" }} />
      <input ref={pdfRef} type="file" accept=".pdf" className="hidden" onChange={e => { const f = e.target.files?.[0]; const row = fileRow.current; if (f && row) upd(row.i, { pdf: f }); e.target.value = "" }} />
      <input ref={dropRef} type="file" multiple accept=".step,.stp,.pdf" className="hidden" onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = "" }} />
      <div
        role="button"
        tabIndex={0}
        onClick={() => dropRef.current?.click()}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") dropRef.current?.click() }}
        onDragEnter={e => { e.preventDefault(); setDrag(true) }}
        onDragOver={e => e.preventDefault()}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }}
        className={`mt-4 grid min-h-[140px] cursor-pointer place-items-center rounded border-2 border-dashed p-6 text-center ${drag ? "border-blue-600 bg-slate-50" : "border-[#e2e8f0] bg-[#f8fafc]"}`}
      >
        <div>
          <UploadCloud className="mx-auto mb-2 text-slate-400" size={28} />
          <div className="text-sm font-medium text-slate-700">拖拽或点击上传 .step / .stp / .pdf</div>
          <div className="mt-1 font-mono text-[10px] text-slate-400">3D · STEP / STP　　2D · PDF　　≤ 100 MB</div>
        </div>
      </div>
    </Card>

    {err && <div className="text-sm text-red-700">{err}</div>}
    <div className="flex justify-end gap-3">
      <Button variant="outline" type="button" onClick={() => go("")}>取消</Button>
      <Button type="button" onClick={submit} disabled={busy}>{busy ? "分析中…" : "开始 AI 分析"}</Button>
    </div>
  </div>
}
