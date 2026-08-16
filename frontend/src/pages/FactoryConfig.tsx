import { useEffect, useState } from "react"
import { Button, Card, Input, Select } from "../components/ui"
import { json } from "../api"

const TABS = ["基本信息", "设备库", "刀具库", "材料价格", "默认报价规则"]

function emptyMachine() {
  return { id: "VM" + String(Date.now()).slice(-4), type: "立式加工中心", axes: 3, max_rpm: 12000, hourly_rate: 80, setup_fee: 200, enabled: 1 }
}

export function FactoryConfig() {
  const [cfg, setCfg] = useState<any>(null)
  const [tab, setTab] = useState(1)
  const [msg, setMsg] = useState("")
  const [err, setErr] = useState("")
  useEffect(() => { json<any>("/factory-config").then(setCfg).catch(e => setErr(e.message)) }, [])
  async function save() {
    try {
      setErr(""); setMsg("")
      const next = await json<any>("/factory-config", { method: "PUT", body: JSON.stringify(cfg) })
      setCfg(next)
      setMsg("已保存，新报价将使用最新规则")
    } catch (e: any) { setErr(e.message) }
  }
  if (!cfg) return <div className="text-sm text-slate-500">{err || "加载中…"}</div>
  const s = cfg.settings || {}
  const machines = cfg.machines || []
  const rates = cfg.rate_table || []
  const materials = cfg.material_prices || []
  return <div className="space-y-5">
    <div className="flex items-end justify-between gap-4">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-500">FACTORY ENGINE</div>
        <h1 className="font-serif mt-2 text-3xl font-semibold tracking-tight text-slate-900">数字工厂配置引擎</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">这些配置会直接参与 AI 报价，请按工厂真实能力维护。</p>
      </div>
      <Button onClick={save}>保存最新配置</Button>
    </div>
    <div className="rounded border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
      当前报价规则版本：工厂默认报价规则 {s.extra?.rules_version || "v1"} ｜ 保存后新询价自动使用最新规则
    </div>
    <div className="grid gap-6 md:grid-cols-[200px_1fr]">
      <div className="space-y-1">
        {TABS.map((t, i) => (
          <button key={t} type="button" onClick={() => setTab(i)}
            className={`block w-full rounded px-3 py-2 text-left text-sm ${tab === i ? "bg-blue-600 text-white" : "text-slate-700 hover:bg-slate-100"}`}>{t}</button>
        ))}
      </div>
      <div>
        {tab === 0 && <Card className="grid gap-3 p-5 md:grid-cols-3">
          <label className="text-xs text-slate-500">利润 %<Input className="mt-1" type="number" value={s.profit_pct ?? 15} onChange={e => setCfg({ ...cfg, settings: { ...s, profit_pct: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">最低收费<Input className="mt-1" type="number" value={s.floor_charge ?? 0} onChange={e => setCfg({ ...cfg, settings: { ...s, floor_charge: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">检测费<Input className="mt-1" type="number" value={s.inspect_fee ?? 60} onChange={e => setCfg({ ...cfg, settings: { ...s, inspect_fee: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">默认批量<Input className="mt-1" type="number" value={s.batch_size ?? 1} onChange={e => setCfg({ ...cfg, settings: { ...s, batch_size: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">默认毛坯<Input className="mt-1" value={s.blank_type || "板料"} onChange={e => setCfg({ ...cfg, settings: { ...s, blank_type: e.target.value } })} /></label>
          <label className="flex items-end gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!s.ignore_available_machines} onChange={e => setCfg({ ...cfg, settings: { ...s, ignore_available_machines: e.target.checked } })} />忽略可用设备</label>
        </Card>}

        {tab === 1 && <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium">可用加工设备</div>
            <button type="button" className="text-xs font-medium text-blue-600" onClick={() => setCfg({ ...cfg, machines: [...machines, emptyMachine()] })}>+ 添加新设备</button>
          </div>
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
              <th className="py-2">设备名称/型号</th><th>类型</th><th>小时成本</th><th>最大转速</th><th>状态</th><th>操作</th>
            </tr></thead>
            <tbody>
              {machines.map((m: any, i: number) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-2 pr-2"><Input value={m.id} onChange={e => { const list = [...machines]; list[i] = { ...m, id: e.target.value }; setCfg({ ...cfg, machines: list }) }} /></td>
                  <td className="pr-2"><Input value={m.type || ""} onChange={e => { const list = [...machines]; list[i] = { ...m, type: e.target.value }; setCfg({ ...cfg, machines: list }) }} /></td>
                  <td className="pr-2"><Input type="number" value={m.hourly_rate ?? 80} onChange={e => { const list = [...machines]; list[i] = { ...m, hourly_rate: Number(e.target.value) }; setCfg({ ...cfg, machines: list }) }} /></td>
                  <td className="pr-2"><Input type="number" value={m.max_rpm ?? 12000} onChange={e => { const list = [...machines]; list[i] = { ...m, max_rpm: Number(e.target.value) }; setCfg({ ...cfg, machines: list }) }} /></td>
                  <td><Select value={m.enabled ? "1" : "0"} onChange={e => { const list = [...machines]; list[i] = { ...m, enabled: Number(e.target.value) }; setCfg({ ...cfg, machines: list }) }}><option value="1">启用</option><option value="0">停用</option></Select></td>
                  <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, machines: machines.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                </tr>
              ))}
              {!machines.length && <tr><td colSpan={6} className="py-8 text-center text-slate-400">还没有设备，点右上角添加</td></tr>}
            </tbody>
          </table>
        </Card>}

        {tab === 2 && <Card className="p-5 text-sm text-slate-600">
          刀具勾选对接现有 tools 目录。当前勾选 {cfg.tools?.length || 0} 条。MVP 先在保存时保留现有勾选。
        </Card>}

        {tab === 3 && <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium">材料价格（元/kg）</div>
            <button type="button" className="text-xs font-medium text-blue-600" onClick={() => setCfg({ ...cfg, material_prices: [...materials, { material_code: "AL6061-T6", price_per_kg: 28, scrap_price_per_kg: 8, enabled: 1 }] })}>+ 添加材料</button>
          </div>
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500"><th className="py-2">材料</th><th>采购价</th><th>废料价</th><th></th></tr></thead>
            <tbody>{materials.map((m: any, i: number) => (
              <tr key={i} className="border-b border-slate-100">
                <td className="py-2 pr-2"><Input value={m.material_code} onChange={e => { const list = [...materials]; list[i] = { ...m, material_code: e.target.value }; setCfg({ ...cfg, material_prices: list }) }} /></td>
                <td className="pr-2"><Input type="number" value={m.price_per_kg} onChange={e => { const list = [...materials]; list[i] = { ...m, price_per_kg: Number(e.target.value) }; setCfg({ ...cfg, material_prices: list }) }} /></td>
                <td className="pr-2"><Input type="number" value={m.scrap_price_per_kg} onChange={e => { const list = [...materials]; list[i] = { ...m, scrap_price_per_kg: Number(e.target.value) }; setCfg({ ...cfg, material_prices: list }) }} /></td>
                <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, material_prices: materials.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
              </tr>
            ))}</tbody>
          </table>
        </Card>}

        {tab === 4 && <Card className="p-5">
          <div className="mb-3 text-sm font-medium">机时费率</div>
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500"><th className="py-2">设备类型</th><th>机时</th><th>调机</th><th>编程</th></tr></thead>
            <tbody>{rates.map((r: any, i: number) => (
              <tr key={r.equipment_type} className="border-b border-slate-100">
                <td className="py-2">{r.equipment_type}</td>
                <td className="pr-2"><Input type="number" value={r.hourly_rate} onChange={e => { const list = [...rates]; list[i] = { ...r, hourly_rate: Number(e.target.value) }; setCfg({ ...cfg, rate_table: list }) }} /></td>
                <td className="pr-2"><Input type="number" value={r.setup_fee} onChange={e => { const list = [...rates]; list[i] = { ...r, setup_fee: Number(e.target.value) }; setCfg({ ...cfg, rate_table: list }) }} /></td>
                <td><Input type="number" value={r.programming_fee_new} onChange={e => { const list = [...rates]; list[i] = { ...r, programming_fee_new: Number(e.target.value) }; setCfg({ ...cfg, rate_table: list }) }} /></td>
              </tr>
            ))}</tbody>
          </table>
        </Card>}
      </div>
    </div>
    {msg && <div className="text-sm text-emerald-700">{msg}</div>}
    {err && <div className="text-sm text-red-700">{err}</div>}
  </div>
}
