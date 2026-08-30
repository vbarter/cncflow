import { useEffect, useState } from "react"
import { Button, Card, Input, Select } from "../components/ui"
import { json } from "../api"

const TABS = ["基本信息", "设备库", "刀具库", "材料价格", "默认报价规则"]
const TABS_MOBILE = ["基本", "设备", "刀具", "材料", "规则"]

type Col = { key: string; label: string; kind?: "num" | "text" }
const RATE: Record<string, { hourly_rate: number; setup_fee: number; axes: number }> = {
  "3轴立式加工中心": { hourly_rate: 120, setup_fee: 200, axes: 3 },
  "4轴立式加工中心": { hourly_rate: 150, setup_fee: 300, axes: 4 },
  "5轴联动加工中心": { hourly_rate: 280, setup_fee: 500, axes: 5 },
  "卧式加工中心": { hourly_rate: 180, setup_fee: 400, axes: 4 },
  "龙门加工中心": { hourly_rate: 220, setup_fee: 600, axes: 3 },
  "精密坐标镗床": { hourly_rate: 350, setup_fee: 250, axes: 3 },
  "电火花成型机EDM": { hourly_rate: 180, setup_fee: 250, axes: 3 },
  "电火花线切割WEDM": { hourly_rate: 60, setup_fee: 250, axes: 4 },
  "车削中心CNC车": { hourly_rate: 100, setup_fee: 150, axes: 2 },
  "车铣复合中心": { hourly_rate: 200, setup_fee: 400, axes: 5 },
  "外圆磨床": { hourly_rate: 160, setup_fee: 250, axes: 2 },
  "平面磨床": { hourly_rate: 140, setup_fee: 250, axes: 3 },
}
const MACHINE_GROUPS: { type: string; cols: Col[] }[] = [
  { type: "3轴立式加工中心", cols: [
    { key: "id", label: "型号" }, { key: "travel_x", label: "X行程", kind: "num" }, { key: "travel_y", label: "Y行程", kind: "num" }, { key: "travel_z", label: "Z行程", kind: "num" },
    { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "torque_nm", label: "扭矩Nm", kind: "num" },
    { key: "magazine", label: "刀库", kind: "num" }, { key: "table", label: "工作台" }, { key: "taper", label: "锥孔" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "4轴立式加工中心", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "axis4", label: "第4轴" },
    { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "magazine", label: "刀库", kind: "num" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "5轴联动加工中心", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "ab_range", label: "AB轴范围" },
    { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "rtcp", label: "RTCP" }, { key: "magazine", label: "刀库", kind: "num" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "卧式加工中心", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "table", label: "工作台" },
    { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "b_axis", label: "B轴" }, { key: "magazine", label: "刀库", kind: "num" }, { key: "pallet", label: "交换台" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "龙门加工中心", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "magazine", label: "刀库", kind: "num" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "精密坐标镗床", cols: [
    { key: "id", label: "型号" }, { key: "travel_x", label: "X行程", kind: "num" }, { key: "travel_y", label: "Y行程", kind: "num" }, { key: "travel_z", label: "Z行程", kind: "num" }, { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" },
  ]},
  { type: "电火花成型机EDM", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "electrode_kg", label: "电极kg", kind: "num" }, { key: "table", label: "工作台" }, { key: "best_ra", label: "最佳Ra um", kind: "num" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "电火花线切割WEDM", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "车削中心CNC车", cols: [
    { key: "id", label: "型号" }, { key: "swing_d", label: "回转直径", kind: "num" }, { key: "turn_len", label: "车削长度", kind: "num" }, { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "turret", label: "刀塔位", kind: "num" }, { key: "c_axis", label: "C轴" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "车铣复合中心", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" }, { key: "ref_price", label: "参考价万", kind: "num" },
  ]},
  { type: "外圆磨床", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" },
  ]},
  { type: "平面磨床", cols: [
    { key: "id", label: "型号" }, { key: "xyz", label: "XYZ行程" }, { key: "max_rpm", label: "转速rpm", kind: "num" }, { key: "power_kw", label: "功率kW", kind: "num" },
  ]},
]

const TOOL_GROUPS: { title: string; types: string[] }[] = [
  { title: "麻花钻", types: ["麻花钻"] },
  { title: "内冷深孔钻", types: ["内冷深孔钻"] },
  { title: "枪钻", types: ["枪钻"] },
  { title: "中心钻", types: ["中心钻"] },
  { title: "微钻", types: ["微钻"] },
  { title: "铰刀", types: ["铰刀"] },
  { title: "镗刀", types: ["粗镗刀", "精镗刀", "超精镗刀", "镗刀"] },
  { title: "平头立铣刀", types: ["平头立铣刀"] },
  { title: "面铣刀", types: ["面铣刀"] },
  { title: "球头立铣刀", types: ["球头立铣刀"] },
  { title: "圆角立铣刀", types: ["圆角立铣刀"] },
  { title: "丝锥", types: ["丝锥"] },
  { title: "螺纹铣刀", types: ["螺纹铣刀"] },
  { title: "倒角刀", types: ["倒角刀"] },
  { title: "砂轮", types: ["砂轮"] },
  { title: "电极", types: ["电极"] },
]

const MATERIAL_TIERS: { title: string; tier: string; warn?: boolean }[] = [
  { title: "常用材料", tier: "common" },
  { title: "扩展材料", tier: "extended", warn: true },
]

function emptyMachine(type: string) {
  const r = RATE[type] || { hourly_rate: 80, setup_fee: 200, axes: 3 }
  return { id: "EQ" + String(Date.now()).slice(-6), type, axes: r.axes, hourly_rate: r.hourly_rate, setup_fee: r.setup_fee, enabled: 1 }
}

function emptyTool(toolType: string) {
  return {
    sku: "TK-NEW-" + String(Date.now()).slice(-6),
    tool_type: toolType,
    category: toolType,
    spec: "",
    diameter_mm: 6, r: 0, flutes: 2, max_ld: 3,
    structure: "标准", base_material: "硬质合金",
    coating: "无涂层", precision_grade: "普通", in_stock: 1,
  }
}

function emptyMaterial(tier: string) {
  return {
    material_code: "", display_name: "", family: "",
    density_g_cm3: 2.7, price_per_kg: 0, scrap_price_per_kg: 0,
    tier, warning: tier === "extended" ? "报价前确认" : "",
    enabled: 1,
  }
}

function toolTypeOf(t: any) {
  return t.tool_type || t.category || ""
}

function materialTierOf(m: any) {
  if (m.tier === "common" || m.tier === "extended" || m.tier === "alias") return m.tier
  if (m.alias_of) return "alias"
  if (m.warning) return "extended"
  return "common"
}

function patchAt(list: any[], globalIndex: number, patch: Record<string, unknown>) {
  const next = [...list]
  next[globalIndex] = { ...list[globalIndex], ...patch }
  return next
}

function CatalogBlock({ title, count, onAdd, children }: { title: string; count: number; onAdd: () => void; children: any }) {
  return (
    <div className="mb-6 rounded border border-[#e2e8f0] bg-white">
      <div className="flex items-center justify-between border-b border-[#e2e8f0] px-4 py-2">
        <div className="text-sm font-medium text-slate-800">{title}<span className="ml-2 text-xs font-normal text-slate-400">{count} 条</span></div>
        <button type="button" className="text-xs font-medium text-blue-600" onClick={onAdd}>+ 添加</button>
      </div>
      <div className="factory-table-scroll max-w-full p-3">{children}</div>
    </div>
  )
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
  const tools = cfg.tools || []
  const rates = cfg.rate_table || []
  const materials = cfg.material_prices || []
  const groupedTypes = new Set(TOOL_GROUPS.flatMap(g => g.types))
  const otherTools = tools.filter((t: any) => !groupedTypes.has(toolTypeOf(t)))

  return <div className="space-y-5 overflow-x-hidden">
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between md:gap-4">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-500">FACTORY ENGINE</div>
        <h1 className="font-serif mt-2 text-3xl font-semibold tracking-tight text-slate-900">数字工厂配置引擎</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">按文档分类维护设备、刀具、材料，保存后直接参与报价。</p>
      </div>
      <Button className="min-h-11 md:min-h-10" onClick={save}>保存最新配置</Button>
    </div>
    <div className="rounded border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
      当前报价规则版本：工厂默认报价规则 {s.extra?.rules_version || "v1"} ｜ 保存后新询价自动使用最新规则
    </div>
    <div className="flex flex-col gap-6 md:grid md:grid-cols-[200px_1fr]">
      <div className="flex shrink-0 flex-wrap gap-1 md:block md:space-y-1">
        {TABS.map((t, i) => (
          <button key={t} type="button" onClick={() => setTab(i)}
            className={`min-h-11 rounded px-3 py-2 text-left text-sm md:block md:w-full md:min-h-0 ${tab === i ? "bg-blue-600 text-white" : "text-slate-700 hover:bg-slate-100"}`}><span className="md:hidden">{TABS_MOBILE[i]}</span><span className="hidden md:inline">{t}</span></button>
        ))}
      </div>
      <div className="min-w-0 w-full">
        {tab === 0 && <Card className="grid gap-3 p-5 md:grid-cols-3">
          <label className="text-xs text-slate-500">利润 %<Input className="mt-1" type="number" value={s.profit_pct ?? 15} onChange={e => setCfg({ ...cfg, settings: { ...s, profit_pct: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">最低收费<Input className="mt-1" type="number" value={s.floor_charge ?? 0} onChange={e => setCfg({ ...cfg, settings: { ...s, floor_charge: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">检测费（自动报价暂不计，待知识库 Word）<Input className="mt-1" type="number" value={s.inspect_fee ?? 0} onChange={e => setCfg({ ...cfg, settings: { ...s, inspect_fee: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">默认批量<Input className="mt-1" type="number" value={s.batch_size ?? 1} onChange={e => setCfg({ ...cfg, settings: { ...s, batch_size: Number(e.target.value) } })} /></label>
          <label className="text-xs text-slate-500">默认毛坯<Input className="mt-1" value={s.blank_type || "板料"} onChange={e => setCfg({ ...cfg, settings: { ...s, blank_type: e.target.value } })} /></label>
          <label className="flex items-end gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!s.ignore_available_machines} onChange={e => setCfg({ ...cfg, settings: { ...s, ignore_available_machines: e.target.checked } })} />忽略可用设备</label>
        </Card>}

        {tab === 1 && <div>
          {MACHINE_GROUPS.map(g => {
            const rows = machines.map((m: any, i: number) => ({ m, i })).filter(({ m }: any) => m.type === g.type)
            return <CatalogBlock key={g.type} title={g.type} count={rows.length} onAdd={() => setCfg({ ...cfg, machines: [...machines, emptyMachine(g.type)] })}>
              <table className="w-full min-w-[960px] text-left text-sm">
                <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
                  {g.cols.map(c => <th key={c.key} className="py-2 pr-2">{c.label}</th>)}
                  <th>小时费率</th><th>调机费</th><th>启用</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {rows.map(({ m, i }: any) => (
                    <tr key={i} className="border-b border-slate-100">
                      {g.cols.map(c => (
                        <td key={c.key} className="py-2 pr-2">
                          <Input type={c.kind === "num" ? "number" : "text"} value={m[c.key] ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { [c.key]: c.kind === "num" ? Number(e.target.value) : e.target.value }) })} />
                        </td>
                      ))}
                      <td className="pr-2"><Input type="number" value={m.hourly_rate ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { hourly_rate: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.setup_fee ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { setup_fee: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Select value={m.enabled ? "1" : "0"} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { enabled: Number(e.target.value) }) })}><option value="1">启用</option><option value="0">停用</option></Select></td>
                      <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, machines: machines.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={g.cols.length + 4} className="py-6 text-center text-slate-400">此类暂无设备</td></tr>}
                </tbody>
              </table>
            </CatalogBlock>
          })}
        </div>}

        {tab === 2 && <div>
          {TOOL_GROUPS.map(g => {
            const rows = tools.map((t: any, i: number) => ({ t, i })).filter(({ t }: any) => g.types.includes(toolTypeOf(t)))
            return <CatalogBlock key={g.title} title={g.title} count={rows.length} onAdd={() => setCfg({ ...cfg, tools: [...tools, emptyTool(g.types[0])] })}>
              <table className="w-full min-w-[960px] text-left text-sm">
                <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
                  <th className="py-2">SKU</th><th>类型</th><th>规格</th><th>d</th><th>r</th><th>材质</th><th>涂层</th><th>刃数</th><th>最大长径比</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {rows.map(({ t, i }: any) => (
                    <tr key={t.sku + "-" + i} className="border-b border-slate-100">
                      <td className="py-2 pr-2"><Input value={t.sku || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { sku: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={toolTypeOf(t)} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { tool_type: e.target.value, category: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={t.spec || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { spec: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" value={t.diameter_mm ?? ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { diameter_mm: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" step="0.1" value={t.r ?? ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { r: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input value={t.base_material || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { base_material: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={t.coating || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { coating: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" value={t.flutes ?? ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { flutes: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={t.max_ld ?? ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { max_ld: Number(e.target.value) }) })} /></td>
                      <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, tools: tools.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={10} className="py-6 text-center text-slate-400">此类暂无刀具</td></tr>}
                </tbody>
              </table>
            </CatalogBlock>
          })}
          {otherTools.length > 0 && <CatalogBlock title="其他" count={otherTools.length} onAdd={() => setCfg({ ...cfg, tools: [...tools, emptyTool("麻花钻")] })}>
            <div className="text-xs text-slate-500">未归入上表的 {otherTools.length} 条，保存后仍在目录里。</div>
          </CatalogBlock>}
        </div>}

        {tab === 3 && <div>
          {MATERIAL_TIERS.map(g => {
            const rows = materials.map((m: any, i: number) => ({ m, i })).filter(({ m }: any) => materialTierOf(m) === g.tier)
            return <CatalogBlock key={g.tier} title={g.title} count={rows.length} onAdd={() => setCfg({ ...cfg, material_prices: [...materials, emptyMaterial(g.tier)] })}>
              {g.warn && <div className="mb-2 text-xs text-amber-700">扩展材料单价波动大，报价前确认。</div>}
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
                  <th className="py-2">编号</th><th>名称</th><th>密度 g/cm³</th><th>单价 ¥/kg</th><th>回收价 ¥/kg</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {rows.map(({ m, i }: any) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-2 pr-2"><Input value={m.material_code} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { material_code: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={m.display_name || ""} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { display_name: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" step="0.01" value={m.density_g_cm3 ?? ""} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { density_g_cm3: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.price_per_kg} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { price_per_kg: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.scrap_price_per_kg} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { scrap_price_per_kg: Number(e.target.value) }) })} /></td>
                      <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, material_prices: materials.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={6} className="py-6 text-center text-slate-400">此类暂无材料</td></tr>}
                </tbody>
              </table>
            </CatalogBlock>
          })}
        </div>}

        {tab === 4 && <Card className="p-5">
          <div className="mb-3 text-sm font-medium">机时费率</div>
          <div className="factory-table-scroll max-w-full">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500"><th className="py-2">设备类型</th><th>机时</th><th>调机</th><th>编程时薪</th></tr></thead>
            <tbody>{rates.map((r: any, i: number) => (
              <tr key={r.equipment_type} className="border-b border-slate-100">
                <td className="py-2">{r.equipment_type}</td>
                <td className="pr-2"><Input type="number" value={r.hourly_rate} onChange={e => { const list = [...rates]; list[i] = { ...r, hourly_rate: Number(e.target.value) }; setCfg({ ...cfg, rate_table: list }) }} /></td>
                <td className="pr-2"><Input type="number" value={r.setup_fee} onChange={e => { const list = [...rates]; list[i] = { ...r, setup_fee: Number(e.target.value) }; setCfg({ ...cfg, rate_table: list }) }} /></td>
                <td><Input type="number" value={r.programming_hourly_rate ?? ""} onChange={e => { const list = [...rates]; list[i] = { ...r, programming_hourly_rate: Number(e.target.value) }; setCfg({ ...cfg, rate_table: list }) }} /></td>
              </tr>
            ))}</tbody>
          </table>
          </div>
        </Card>}
      </div>
    </div>
    {msg && <div className="text-sm text-emerald-700">{msg}</div>}
    {err && <div className="text-sm text-red-700">{err}</div>}
  </div>
}
