import { useEffect, useState } from "react"
import { Button, Card, Input, Select } from "../components/ui"
import { json } from "../api"

const TABS = ["基本信息", "设备库", "刀具库", "材料价格", "默认报价规则"]

const MACHINE_GROUPS = [
  "3轴立式加工中心", "4轴立式加工中心", "5轴联动加工中心", "卧式加工中心",
  "龙门加工中心", "精密坐标镗床", "电火花成型机EDM", "电火花线切割WEDM",
  "车削中心CNC车", "车铣复合中心", "外圆磨床", "平面磨床",
]

const TOOL_GROUPS: { title: string; cats: string[] }[] = [
  { title: "中心钻", cats: ["中心钻"] },
  { title: "麻花钻", cats: ["钻头"] },
  { title: "深孔钻", cats: ["U钻"] },
  { title: "枪钻", cats: ["枪钻"] },
  { title: "铰刀", cats: ["铰刀"] },
  { title: "镗刀", cats: ["镗刀"] },
  { title: "铣刀", cats: ["平底立铣刀", "螺纹铣刀"] },
  { title: "丝锥", cats: ["丝锥"] },
  { title: "倒角刀", cats: ["倒角刀"] },
]

const MATERIAL_FAMILIES = ["铝合金", "普通碳钢", "不锈钢", "钛合金", "铸铁", "铜合金", "工程塑料", "合金钢"]

function emptyMachine(type: string) {
  const axes = type.startsWith("5") ? 5 : type.startsWith("4") || type.includes("卧") ? 4 : 3
  return {
    id: "EQ" + String(Date.now()).slice(-6),
    type,
    axes,
    travel_x: 800, travel_y: 500, travel_z: 500,
    max_rpm: 12000, power_kw: 11, tool_change_s: 3.5,
    fixture_mode: "虎钳", hourly_rate: 80, setup_fee: 200, enabled: 1,
  }
}

function emptyTool(category: string) {
  return {
    sku: "SKU-NEW-" + String(Date.now()).slice(-6),
    category,
    diameter_mm: 3, structure: "标准", base_material: "硬质合金",
    coating: "无涂层", precision_grade: "普通", in_stock: 1,
  }
}

function emptyMaterial(family: string) {
  return { material_code: "", family, density_g_cm3: 2.7, price_per_kg: 0, scrap_price_per_kg: 0, enabled: 1 }
}

function inferFamily(code: string, family?: string) {
  if (family && MATERIAL_FAMILIES.includes(family)) return family
  const s = String(code || "")
  if (/铝|6061|7075|AL/i.test(s)) return "铝合金"
  if (/不锈钢|304|316|SUS/i.test(s)) return "不锈钢"
  if (/钛|TC4|Ti/i.test(s)) return "钛合金"
  if (/铸铁|HT/i.test(s)) return "铸铁"
  if (/铜|黄铜|紫铜|H59|T2/i.test(s)) return "铜合金"
  if (/POM|ABS|尼龙|塑料|PA/i.test(s)) return "工程塑料"
  if (/合金钢|40Cr|42Cr/i.test(s)) return "合金钢"
  if (/钢/.test(s)) return "普通碳钢"
  return "普通碳钢"
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
      <div className="overflow-x-auto p-3">{children}</div>
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
  const groupedCats = new Set(TOOL_GROUPS.flatMap(g => g.cats))
  const otherTools = tools.filter((t: any) => !groupedCats.has(t.category))

  return <div className="space-y-5">
    <div className="flex items-end justify-between gap-4">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[.18em] text-slate-500">FACTORY ENGINE</div>
        <h1 className="font-serif mt-2 text-3xl font-semibold tracking-tight text-slate-900">数字工厂配置引擎</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">按文档分类维护设备、刀具、材料，保存后直接参与报价。</p>
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

        {tab === 1 && <div>
          {MACHINE_GROUPS.map(type => {
            const rows = machines.map((m: any, i: number) => ({ m, i })).filter(({ m }: any) => m.type === type)
            return <CatalogBlock key={type} title={type} count={rows.length} onAdd={() => setCfg({ ...cfg, machines: [...machines, emptyMachine(type)] })}>
              <table className="w-full min-w-[1100px] text-left text-sm">
                <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
                  <th className="py-2">型号</th><th>轴数</th><th>行程X</th><th>行程Y</th><th>行程Z</th>
                  <th>最大转速</th><th>功率kW</th><th>换刀s</th><th>装夹</th><th>小时费率</th><th>调机费</th><th>启用</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {rows.map(({ m, i }: any) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-2 pr-2"><Input value={m.id} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { id: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.axes ?? 3} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { axes: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.travel_x ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { travel_x: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.travel_y ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { travel_y: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.travel_z ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { travel_z: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.max_rpm ?? 12000} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { max_rpm: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.power_kw ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { power_kw: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.tool_change_s ?? ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { tool_change_s: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input value={m.fixture_mode || ""} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { fixture_mode: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.hourly_rate ?? 80} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { hourly_rate: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.setup_fee ?? 200} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { setup_fee: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Select value={m.enabled ? "1" : "0"} onChange={e => setCfg({ ...cfg, machines: patchAt(machines, i, { enabled: Number(e.target.value) }) })}><option value="1">启用</option><option value="0">停用</option></Select></td>
                      <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, machines: machines.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={13} className="py-6 text-center text-slate-400">此类暂无设备</td></tr>}
                </tbody>
              </table>
            </CatalogBlock>
          })}
        </div>}

        {tab === 2 && <div>
          {TOOL_GROUPS.map(g => {
            const rows = tools.map((t: any, i: number) => ({ t, i })).filter(({ t }: any) => g.cats.includes(t.category))
            return <CatalogBlock key={g.title} title={g.title} count={rows.length} onAdd={() => setCfg({ ...cfg, tools: [...tools, emptyTool(g.cats[0])] })}>
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
                  <th className="py-2">SKU</th><th>类型</th><th>直径</th><th>结构</th><th>材质</th><th>涂层</th><th>精度</th><th>在库</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {rows.map(({ t, i }: any) => (
                    <tr key={t.sku + "-" + i} className="border-b border-slate-100">
                      <td className="py-2 pr-2"><Input value={t.sku || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { sku: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={t.category || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { category: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" value={t.diameter_mm ?? ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { diameter_mm: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input value={t.structure || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { structure: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={t.base_material || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { base_material: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={t.coating || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { coating: e.target.value }) })} /></td>
                      <td className="pr-2"><Input value={t.precision_grade || ""} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { precision_grade: e.target.value }) })} /></td>
                      <td className="pr-2"><Select value={t.in_stock ? "1" : "0"} onChange={e => setCfg({ ...cfg, tools: patchAt(tools, i, { in_stock: Number(e.target.value) }) })}><option value="1">在库</option><option value="0">缺货</option></Select></td>
                      <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, tools: tools.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={9} className="py-6 text-center text-slate-400">此类暂无刀具</td></tr>}
                </tbody>
              </table>
            </CatalogBlock>
          })}
          {otherTools.length > 0 && <CatalogBlock title="其他" count={otherTools.length} onAdd={() => setCfg({ ...cfg, tools: [...tools, emptyTool("钻头")] })}>
            <div className="text-xs text-slate-500">未归入上表的 {otherTools.length} 条，保存后仍在目录里。</div>
          </CatalogBlock>}
        </div>}

        {tab === 3 && <div>
          {MATERIAL_FAMILIES.map(family => {
            const rows = materials.map((m: any, i: number) => ({ m, i })).filter(({ m }: any) => inferFamily(m.material_code, m.family) === family)
            return <CatalogBlock key={family} title={family} count={rows.length} onAdd={() => setCfg({ ...cfg, material_prices: [...materials, emptyMaterial(family)] })}>
              <table className="w-full text-left text-sm">
                <thead><tr className="border-b border-[#e2e8f0] text-xs text-slate-500">
                  <th className="py-2">牌号</th><th>密度 g/cm³</th><th>采购价</th><th>废料回收</th><th>启用</th><th>操作</th>
                </tr></thead>
                <tbody>
                  {rows.map(({ m, i }: any) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-2 pr-2"><Input value={m.material_code} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { material_code: e.target.value }) })} /></td>
                      <td className="pr-2"><Input type="number" step="0.01" value={m.density_g_cm3 ?? ""} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { density_g_cm3: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.price_per_kg} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { price_per_kg: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Input type="number" value={m.scrap_price_per_kg} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { scrap_price_per_kg: Number(e.target.value) }) })} /></td>
                      <td className="pr-2"><Select value={m.enabled ? "1" : "0"} onChange={e => setCfg({ ...cfg, material_prices: patchAt(materials, i, { enabled: Number(e.target.value) }) })}><option value="1">启用</option><option value="0">停用</option></Select></td>
                      <td><button type="button" className="text-xs text-slate-400 hover:text-red-500" onClick={() => setCfg({ ...cfg, material_prices: materials.filter((_: any, idx: number) => idx !== i) })}>删除</button></td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={6} className="py-6 text-center text-slate-400">此族暂无材料</td></tr>}
                </tbody>
              </table>
            </CatalogBlock>
          })}
        </div>}

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
