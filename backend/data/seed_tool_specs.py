"""导入《3-CNC刀具库》中的孔加工相关标准规格（不伪造真实 SKU）。"""
import json


SOURCE_ID = "doc3_tool_catalog"


def _rows():
    rows = []

    def add(category, diameter=None, base=None, coating=None, thread=None, angle=None, extra=None):
        key = thread if thread else (f"D{diameter:g}" if diameter is not None else "NA")
        if angle is not None:
            key += f"-A{angle:g}"
        spec_id = f"DOC3-{category}-{key}-{len(rows)+1:03d}"
        rows.append((spec_id, category, diameter, thread, angle, None, base, coating, None,
                     SOURCE_ID, "catalog_unverified", json.dumps(extra or {}, ensure_ascii=False)))

    # 平刀用于盲孔平底修底。涂层字段保留原文的可选组合文字。
    for d in [0.5, 0.8, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32]:
        coat = "无涂层" if d < 1 else ("TiB2/TiAlN" if d < 10 else "TiAlN/AlTiN")
        add("平底立铣刀", d, "硬质合金", coat)
    for d in [0.2, 0.3, 0.5, 0.8, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.2, 4.5, 5, 5.5, 6,
              6.8, 7, 8, 8.5, 9, 10, 10.2, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40]:
        add("钻头", d, "高速钢/硬质合金", "TiN")
    for d in [2, 3, 4, 5, 6, 8, 10, 12, 16, 20]:
        add("铰刀", d, "高速钢", "TiN")
    for spec in ["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"]:
        add("丝锥", base="PM-HSS", coating="TiN", thread=spec)
    for spec in ["M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"]:
        add("螺纹铣刀", base="硬质合金", coating="AlTiN", thread=spec)
    for d, angle in [(4,45),(6,45),(8,45),(10,45),(12,45),(16,45),(20,45),(6,60),(10,60),(16,60)]:
        add("倒角刀", d, "硬质合金", "TiAlN", angle=angle)
    return rows


def seed_tool_specs(conn) -> int:
    conn.execute(
        "INSERT INTO material_sources(source_id,title,source_type,locator,license,revision,authority) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO NOTHING",
        (SOURCE_ID, "3-CNC刀具库 (1).docx", "user_document", "3-CNC刀具库 (1).docx", None, "2026-06-30", "catalog_unverified"),
    )
    conn.executemany(
        "INSERT INTO tool_specs(spec_id,category,diameter_mm,thread_spec,angle_deg,structure,base_material,coating,"
        "precision_grade,source_id,verification_status,extra_attrs) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(spec_id) DO UPDATE SET diameter_mm=excluded.diameter_mm,thread_spec=excluded.thread_spec,"
        "angle_deg=excluded.angle_deg,base_material=excluded.base_material,coating=excluded.coating,"
        "verification_status=excluded.verification_status,extra_attrs=excluded.extra_attrs",
        _rows(),
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM tool_specs WHERE source_id=?", (SOURCE_ID,)).fetchone()[0]
