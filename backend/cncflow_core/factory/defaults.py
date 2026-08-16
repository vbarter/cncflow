"""工时费率表缺省（工厂可改）。"""

RATE_TABLE = [
    {"equipment_type": "3轴立式加工中心", "hourly_rate": 120, "setup_fee": 200, "programming_fee_new": 300},
    {"equipment_type": "4轴立式加工中心", "hourly_rate": 150, "setup_fee": 300, "programming_fee_new": 500},
    {"equipment_type": "5轴联动加工中心", "hourly_rate": 280, "setup_fee": 500, "programming_fee_new": 800},
    {"equipment_type": "卧式加工中心", "hourly_rate": 180, "setup_fee": 400, "programming_fee_new": 300},
    {"equipment_type": "龙门加工中心", "hourly_rate": 220, "setup_fee": 600, "programming_fee_new": 300},
    {"equipment_type": "精密坐标镗床", "hourly_rate": 350, "setup_fee": 250, "programming_fee_new": 300},
    {"equipment_type": "电火花成型机EDM", "hourly_rate": 180, "setup_fee": 250, "programming_fee_new": 500},
    {"equipment_type": "电火花线切割WEDM", "hourly_rate": 60, "setup_fee": 250, "programming_fee_new": 300},
    {"equipment_type": "车削中心CNC车", "hourly_rate": 100, "setup_fee": 150, "programming_fee_new": 300},
    {"equipment_type": "车铣复合中心", "hourly_rate": 200, "setup_fee": 400, "programming_fee_new": 800},
    {"equipment_type": "外圆磨床", "hourly_rate": 160, "setup_fee": 250, "programming_fee_new": 300},
    {"equipment_type": "平面磨床", "hourly_rate": 140, "setup_fee": 250, "programming_fee_new": 300},
]

MACHINE_SEEDS = [
    # 3轴《CNC加工设备库0815》
    {"id": "VMC850E", "type": "3轴立式加工中心", "axes": 3, "travel_x": 850, "travel_y": 505, "travel_z": 505, "max_rpm": 12000, "power_kw": 7.5, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 70, "magazine": 24, "table": "1000x520", "taper": "BT40", "ref_price": 28}},
    {"id": "VMC1160", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1100, "travel_y": 600, "travel_z": 600, "max_rpm": 10000, "power_kw": 11, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 120, "magazine": 32, "table": "1250x600", "taper": "BT40", "ref_price": 35}},
    {"id": "VMC1370", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1300, "travel_y": 700, "travel_z": 700, "max_rpm": 8000, "power_kw": 15, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 180, "magazine": 36, "table": "1400x700", "taper": "BT40", "ref_price": 42}},
    {"id": "VMC1580", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1500, "travel_y": 800, "travel_z": 800, "max_rpm": 8000, "power_kw": 18.5, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 220, "magazine": 40, "table": "1600x800", "taper": "BT50", "ref_price": 55}},
    {"id": "VMC1813", "type": "3轴立式加工中心", "axes": 3, "travel_x": 1800, "travel_y": 1300, "travel_z": 900, "max_rpm": 6000, "power_kw": 22, "hourly_rate": 120, "setup_fee": 200, "enabled": 1, "extra": {"torque_nm": 350, "magazine": 50, "table": "2000x1300", "taper": "BT50", "ref_price": 85}},
    # 4轴
    {"id": "VMC850E+HRV160A", "type": "4轴立式加工中心", "axes": 4, "travel_x": 850, "travel_y": 500, "travel_z": 505, "max_rpm": 12000, "power_kw": 7.5, "hourly_rate": 150, "setup_fee": 300, "enabled": 1, "extra": {"xyz": "850x500x505", "axis4": "160液压转台", "magazine": 24, "ref_price": 38}},
    {"id": "VMC1160+HRV210A", "type": "4轴立式加工中心", "axes": 4, "travel_x": 1100, "travel_y": 600, "travel_z": 600, "max_rpm": 10000, "power_kw": 11, "hourly_rate": 150, "setup_fee": 300, "enabled": 1, "extra": {"xyz": "1100x600x600", "axis4": "210液压转台", "magazine": 32, "ref_price": 48}},
    {"id": "TV855S", "type": "4轴立式加工中心", "axes": 4, "travel_x": 850, "travel_y": 505, "travel_z": 560, "max_rpm": 24000, "power_kw": 5.5, "hourly_rate": 150, "setup_fee": 300, "enabled": 1, "extra": {"xyz": "850x505x560", "axis4": "数控A轴转台", "magazine": 21, "ref_price": 52}},
    # 5轴
    {"id": "U600", "type": "5轴联动加工中心", "axes": 5, "travel_x": 600, "travel_y": 550, "travel_z": 450, "max_rpm": 24000, "power_kw": 11, "hourly_rate": 280, "setup_fee": 500, "enabled": 1, "extra": {"xyz": "600x550x450", "ab_range": "-120~+110/C360", "rtcp": "支持", "magazine": 30, "ref_price": 120}},
    {"id": "MU-S600", "type": "5轴联动加工中心", "axes": 5, "travel_x": 600, "travel_y": 560, "travel_z": 500, "max_rpm": 24000, "power_kw": 13.5, "hourly_rate": 280, "setup_fee": 500, "enabled": 1, "extra": {"xyz": "600x560x500", "ab_range": "+-110/C360", "rtcp": "支持", "magazine": 40, "ref_price": 145}},
    {"id": "DMU65", "type": "5轴联动加工中心", "axes": 5, "travel_x": 650, "travel_y": 520, "travel_z": 560, "max_rpm": 18000, "power_kw": 15, "hourly_rate": 280, "setup_fee": 500, "enabled": 1, "extra": {"xyz": "650x520x560", "ab_range": "+-110/C360", "rtcp": "支持", "magazine": 30, "ref_price": 168}},
    # 卧加
    {"id": "HWC500", "type": "卧式加工中心", "axes": 4, "travel_x": 560, "travel_y": 560, "travel_z": 560, "max_rpm": 10000, "power_kw": 11, "hourly_rate": 180, "setup_fee": 400, "enabled": 1, "extra": {"xyz": "560x560x560", "table": "500x500", "b_axis": "1度x360", "magazine": 40, "pallet": "单", "ref_price": 75}},
    {"id": "HWC630", "type": "卧式加工中心", "axes": 4, "travel_x": 750, "travel_y": 750, "travel_z": 720, "max_rpm": 8000, "power_kw": 18.5, "hourly_rate": 180, "setup_fee": 400, "enabled": 1, "extra": {"xyz": "750x750x720", "table": "630x630", "b_axis": "1度x360", "magazine": 60, "pallet": "双", "ref_price": 95}},
    {"id": "HWC800", "type": "卧式加工中心", "axes": 4, "travel_x": 1000, "travel_y": 800, "travel_z": 850, "max_rpm": 6000, "power_kw": 22, "hourly_rate": 180, "setup_fee": 400, "enabled": 1, "extra": {"xyz": "1000x800x850", "table": "800x800", "b_axis": "1度x360", "magazine": 80, "pallet": "双", "ref_price": 135}},
    # 龙门
    {"id": "GMC2012", "type": "龙门加工中心", "axes": 3, "travel_x": 2000, "travel_y": 1200, "travel_z": 800, "max_rpm": 6000, "power_kw": 22, "hourly_rate": 220, "setup_fee": 600, "enabled": 1, "extra": {"xyz": "2000x1200x800", "magazine": 30, "ref_price": 120}},
    {"id": "GMC3018", "type": "龙门加工中心", "axes": 3, "travel_x": 3000, "travel_y": 1800, "travel_z": 1200, "max_rpm": 4000, "power_kw": 30, "hourly_rate": 220, "setup_fee": 600, "enabled": 1, "extra": {"xyz": "3000x1800x1200", "magazine": 40, "ref_price": 185}},
    {"id": "GMC4022", "type": "龙门加工中心", "axes": 3, "travel_x": 4000, "travel_y": 2200, "travel_z": 1500, "max_rpm": 4000, "power_kw": 37, "hourly_rate": 220, "setup_fee": 600, "enabled": 1, "extra": {"xyz": "4000x2200x1500", "magazine": 50, "ref_price": 260}},
    # EDM
    {"id": "GF-C30", "type": "电火花成型机EDM", "axes": 3, "travel_x": 600, "travel_y": 400, "travel_z": 350, "hourly_rate": 180, "setup_fee": 250, "enabled": 1, "extra": {"xyz": "600x400x350", "electrode_kg": 200, "table": "800x400", "best_ra": 0.1, "ref_price": 25}},
    {"id": "Sodick-ALN40S", "type": "电火花成型机EDM", "axes": 3, "travel_x": 400, "travel_y": 250, "travel_z": 250, "hourly_rate": 180, "setup_fee": 250, "enabled": 1, "extra": {"xyz": "400x250x250", "electrode_kg": 50, "table": "450x250", "best_ra": 0.05, "ref_price": 18}},
    {"id": "EDS40S", "type": "电火花成型机EDM", "axes": 3, "travel_x": 400, "travel_y": 300, "travel_z": 280, "hourly_rate": 180, "setup_fee": 250, "enabled": 1, "extra": {"xyz": "400x300x280", "electrode_kg": 30, "table": "420x300", "best_ra": 0.2, "ref_price": 8}},
    # 车削
    {"id": "CK6150", "type": "车削中心CNC车", "axes": 2, "max_rpm": 4000, "power_kw": 7.5, "hourly_rate": 100, "setup_fee": 150, "enabled": 1, "extra": {"swing_d": 520, "turn_len": 1000, "turret": 12, "c_axis": "有", "ref_price": 18}},
    {"id": "CK6180", "type": "车削中心CNC车", "axes": 2, "max_rpm": 3000, "power_kw": 15, "hourly_rate": 100, "setup_fee": 150, "enabled": 1, "extra": {"swing_d": 800, "turn_len": 1500, "turret": 8, "c_axis": "有", "ref_price": 28}},
    {"id": "CTX1250", "type": "车削中心CNC车", "axes": 2, "max_rpm": 5000, "power_kw": 20, "hourly_rate": 100, "setup_fee": 150, "enabled": 1, "extra": {"swing_d": 660, "turn_len": 1250, "turret": 12, "c_axis": "有Y轴", "ref_price": 55}},
]

# 《材料单价配置表0815》常用 10 + 扩展 8。旧牌号走 MATERIAL_ALIASES，现网报价不断。
MATERIAL_PRICES = [
    {"material_code": "AL-01", "display_name": "6061-T6铝合金", "family": "铝合金", "density_g_cm3": 2.70, "price_per_kg": 22, "scrap_price_per_kg": 8, "recycle_rate": 0.85, "tier": "common"},
    {"material_code": "AL-02", "display_name": "7075-T6铝合金", "family": "铝合金", "density_g_cm3": 2.81, "price_per_kg": 28, "scrap_price_per_kg": 10, "recycle_rate": 0.82, "tier": "common"},
    {"material_code": "ST-01", "display_name": "45#钢(调质)", "family": "普通碳钢", "density_g_cm3": 7.85, "price_per_kg": 5.5, "scrap_price_per_kg": 1.8, "recycle_rate": 0.90, "tier": "common"},
    {"material_code": "ST-02", "display_name": "40Cr合金钢", "family": "合金钢", "density_g_cm3": 7.85, "price_per_kg": 7.0, "scrap_price_per_kg": 2.2, "recycle_rate": 0.88, "tier": "common"},
    {"material_code": "SS-01", "display_name": "304不锈钢", "family": "不锈钢", "density_g_cm3": 7.93, "price_per_kg": 18, "scrap_price_per_kg": 3.5, "recycle_rate": 0.82, "tier": "common"},
    {"material_code": "SS-02", "display_name": "316L不锈钢", "family": "不锈钢", "density_g_cm3": 7.98, "price_per_kg": 26, "scrap_price_per_kg": 4.5, "recycle_rate": 0.80, "tier": "common"},
    {"material_code": "TI-01", "display_name": "TC4钛合金", "family": "钛合金", "density_g_cm3": 4.43, "price_per_kg": 380, "scrap_price_per_kg": 95, "recycle_rate": 0.70, "tier": "common"},
    {"material_code": "CU-01", "display_name": "T2紫铜", "family": "铜合金", "density_g_cm3": 8.96, "price_per_kg": 62, "scrap_price_per_kg": 48, "recycle_rate": 0.90, "tier": "common"},
    {"material_code": "CU-02", "display_name": "H62黄铜", "family": "铜合金", "density_g_cm3": 8.43, "price_per_kg": 42, "scrap_price_per_kg": 28, "recycle_rate": 0.88, "tier": "common"},
    {"material_code": "FE-01", "display_name": "HT250灰铸铁", "family": "铸铁", "density_g_cm3": 7.20, "price_per_kg": 4.5, "scrap_price_per_kg": 1.2, "recycle_rate": 0.70, "tier": "common"},
    {"material_code": "AL-03", "display_name": "2024-T4铝", "family": "铝合金", "density_g_cm3": 2.78, "price_per_kg": 32, "scrap_price_per_kg": 11, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "SS-03", "display_name": "17-4PH不锈钢", "family": "不锈钢", "density_g_cm3": 7.78, "price_per_kg": 45, "scrap_price_per_kg": 10, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "TI-02", "display_name": "TA2纯钛", "family": "钛合金", "density_g_cm3": 4.51, "price_per_kg": 280, "scrap_price_per_kg": 80, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "CU-03", "display_name": "铍铜C17200", "family": "铜合金", "density_g_cm3": 8.25, "price_per_kg": 520, "scrap_price_per_kg": 180, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "W-01", "display_name": "硬质合金YG8", "family": "硬质合金", "density_g_cm3": 14.6, "price_per_kg": 320, "scrap_price_per_kg": 120, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "PL-01", "display_name": "ABS塑料", "family": "工程塑料", "density_g_cm3": 1.05, "price_per_kg": 15, "scrap_price_per_kg": 0.5, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "PL-02", "display_name": "PEEK", "family": "工程塑料", "density_g_cm3": 1.30, "price_per_kg": 580, "scrap_price_per_kg": 50, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
    {"material_code": "MD-01", "display_name": "Cr12MoV模具钢", "family": "合金钢", "density_g_cm3": 7.85, "price_per_kg": 18, "scrap_price_per_kg": 5.0, "recycle_rate": None, "tier": "extended", "warning": "报价前确认"},
]

# 现网零件仍写「钢」「铝合金」等旧牌号，指向 0815 编号，报价不断。
MATERIAL_ALIASES = {
    "钢": "ST-01",
    "普通碳钢": "ST-01",
    "铝合金": "AL-01",
    "AL6061-T6": "AL-01",
    "AL7075": "AL-02",
    "不锈钢": "SS-01",
    "SUS304": "SS-01",
    "POM": "PL-01",
}

# 刀具类型 → 孔/报价匹配用的 category（process_category）
TOOL_TYPE_CATEGORY = {
    "麻花钻": "钻头",
    "微钻": "钻头",
    "内冷深孔钻": "U钻",
    "枪钻": "枪钻",
    "中心钻": "中心钻",
    "铰刀": "铰刀",
    "粗镗刀": "镗刀",
    "精镗刀": "镗刀",
    "超精镗刀": "镗刀",
    "平头立铣刀": "平底立铣刀",
    "面铣刀": "平底立铣刀",
    "球头立铣刀": "平底立铣刀",
    "圆角立铣刀": "平底立铣刀",
    "丝锥": "丝锥",
    "螺纹铣刀": "螺纹铣刀",
    "倒角刀": "倒角刀",
    "砂轮": "砂轮",
    "电极": "电极",
}

def _tool(sku, tool_type, spec, d, r, material, coating, flutes, max_ld):
    structure = "内冷" if tool_type == "内冷深孔钻" else ("枪钻" if tool_type == "枪钻" else "标准")
    base = {"HSS": "高速钢"}.get(material, material)
    coat = "无涂层" if coating in {"无", "", None} else coating
    return {
        "sku": sku,
        "category": TOOL_TYPE_CATEGORY[tool_type],
        "tool_type": tool_type,
        "spec": spec,
        "diameter_mm": d,
        "r": r,
        "base_material": base,
        "coating": coat,
        "flutes": flutes,
        "max_ld": max_ld,
        "structure": structure,
        "precision_grade": "普通",
        "in_stock": 1,
    }

# 《刀具SKU目录》TK-001～038，清单里的 TK-039 也留。
TOOL_SEEDS = [
    _tool("TK-001", "麻花钻", "Ø3", 3, 0, "HSS", "无", 2, 3),
    _tool("TK-002", "麻花钻", "Ø3", 3, 0, "硬质合金", "无", 2, 3),
    _tool("TK-003", "麻花钻", "Ø6", 6, 0, "硬质合金", "无", 2, 3),
    _tool("TK-004", "麻花钻", "Ø6", 6, 0, "硬质合金", "TiAlN", 2, 3),
    _tool("TK-005", "麻花钻", "Ø10", 10, 0, "硬质合金", "无", 2, 3),
    _tool("TK-006", "麻花钻", "Ø10", 10, 0, "硬质合金", "AlTiN", 2, 3),
    _tool("TK-007", "麻花钻", "Ø16", 16, 0, "硬质合金", "无", 2, 3),
    _tool("TK-015", "麻花钻", "Ø6", 6, 0, "CBN", "无", 2, 5),
    _tool("TK-039", "麻花钻", "Ø20", 20, 0, "硬质合金", "无", 2, 3),
    _tool("TK-008", "内冷深孔钻", "Ø6", 6, 0, "硬质合金", "TiAlN", 2, 10),
    _tool("TK-009", "内冷深孔钻", "Ø10", 10, 0, "硬质合金", "AlTiN", 2, 10),
    _tool("TK-010", "枪钻", "Ø6", 6, 0, "硬质合金", "无", 1, 40),
    _tool("TK-011", "枪钻", "Ø10", 10, 0, "硬质合金", "无", 1, 40),
    _tool("TK-012", "中心钻", "Ø3", 3, 0, "硬质合金", "无", 2, 2),
    _tool("TK-013", "微钻", "Ø0.5", 0.5, 0, "硬质合金", "无", 2, 3),
    _tool("TK-014", "微钻", "Ø0.8", 0.8, 0, "硬质合金", "无", 2, 3),
    _tool("TK-016", "铰刀", "Ø6", 6, 0, "硬质合金", "无", 6, 3),
    _tool("TK-017", "铰刀", "Ø10", 10, 0, "硬质合金", "无", 6, 3),
    _tool("TK-018", "铰刀", "Ø6", 6, 0, "硬质合金", "TiAlN", 6, 3),
    _tool("TK-019", "粗镗刀", "Ø20-50可调", 0, 0, "硬质合金", "无", 1, 0),
    _tool("TK-020", "精镗刀", "Ø20-50可调", 0, 0, "硬质合金", "无", 1, 0),
    _tool("TK-021", "超精镗刀", "Ø20-40可调", 0, 0, "CBN", "无", 1, 0),
    _tool("TK-022", "平头立铣刀", "Ø6", 6, 0, "硬质合金", "无", 3, 3),
    _tool("TK-023", "平头立铣刀", "Ø6", 6, 0, "硬质合金", "AlTiN", 3, 3),
    _tool("TK-024", "平头立铣刀", "Ø10", 10, 0, "硬质合金", "无", 3, 3),
    _tool("TK-025", "平头立铣刀", "Ø10", 10, 0, "硬质合金", "AlTiN", 3, 3),
    _tool("TK-026", "平头立铣刀", "Ø12", 12, 0, "CBN", "无", 4, 3),
    _tool("TK-027", "面铣刀", "Ø50", 50, 0, "硬质合金", "无", 5, 0),
    _tool("TK-028", "面铣刀", "Ø80", 80, 0, "硬质合金", "无", 6, 0),
    _tool("TK-029", "球头立铣刀", "R3(Ø6)", 6, 3, "硬质合金", "无", 2, 3),
    _tool("TK-030", "球头立铣刀", "R5(Ø10)", 10, 5, "硬质合金", "AlTiN", 2, 3),
    _tool("TK-031", "球头立铣刀", "R1(Ø2)", 2, 1, "硬质合金", "无", 2, 3),
    _tool("TK-032", "圆角立铣刀", "Ø6(R0.5)", 6, 0.5, "硬质合金", "无", 3, 3),
    _tool("TK-033", "丝锥", "M8×1.25", 8, 0, "硬质合金", "TiAlN", 3, 0),
    _tool("TK-034", "丝锥", "M10×1.5", 10, 0, "硬质合金", "TiAlN", 3, 0),
    _tool("TK-035", "螺纹铣刀", "Ø6通用", 6, 0, "硬质合金", "AlTiN", 1, 0),
    _tool("TK-036", "倒角刀", "Ø6(90°)", 6, 0, "硬质合金", "无", 2, 0),
    _tool("TK-037", "砂轮", "Ø50", 50, 0, "砂轮", "无", 1, 0),
    _tool("TK-038", "电极", "铜", 0, 0, "电解铜", "无", 0, 0),
]

