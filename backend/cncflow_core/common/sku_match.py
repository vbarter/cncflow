"""SKU 全等匹配（文档2第三步）：5 项硬性属性全部达标才保留，任一不达标剔除。

倒角刀/中心钻直径"不限定，按孔口规格选型"→ relaxed 模式放宽直径与精度，只匹配
大类 + 基材 + 涂层。
"""
import sqlite3

from .models import ToolAttrs, ToolRequirement


def _catalog_option_allowed(raw_value, allowed: list) -> bool:
    if not raw_value:
        return True  # 未知字段只能进入 catalog_only，并要求人工确认
    aliases = {"Carbide": "硬质合金", "HSS": "高速钢", "PM-HSS": "高速钢", "Uncoated": "无涂层"}
    tokens = [aliases.get(token.strip(), token.strip()) for token in str(raw_value).split("/")]
    return any(token in allowed for token in tokens)


def match_skus(conn: sqlite3.Connection, attrs: ToolAttrs, relaxed: bool = False) -> list:
    if relaxed or attrs.nominal_diameter_mm is None:
        rows = conn.execute(
            "SELECT sku FROM tools WHERE category=? AND base_material=? AND coating=? "
            "AND in_stock=1 ORDER BY sku",
            (attrs.category, attrs.base_material, attrs.coating),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sku FROM tools WHERE category=? AND ABS(diameter_mm-?)<0.001 AND structure=? "
            "AND base_material=? AND coating=? AND precision_grade=? AND in_stock=1 ORDER BY sku",
            (
                attrs.category,
                attrs.nominal_diameter_mm,
                attrs.structure,
                attrs.base_material,
                attrs.coating,
                attrs.precision_grade,
            ),
        ).fetchall()
    return [r["sku"] for r in rows]


def match_with_status(conn: sqlite3.Connection, attrs: ToolAttrs, relaxed: bool = False):
    """返回 (sku_list, match_status, missing_detail)。"""
    skus = match_skus(conn, attrs, relaxed)
    if skus:
        return skus, "matched", None
    detail = (
        f"库存无匹配 SKU：{attrs.category} D={attrs.nominal_diameter_mm} "
        f"{attrs.structure}/{attrs.base_material}/{attrs.coating}/{attrs.precision_grade}；"
        "需定制或调整工艺（文档2：无库存则高成本可加工，无定制渠道则不可加工）"
    )
    return [], "missing", detail


def match_candidates(conn: sqlite3.Connection, requirement: ToolRequirement, relaxed: bool = False,
                     thread_spec: str = None, limit: int = 50) -> list:
    """分层返回真实/模拟 SKU 与目录规格；未知目录字段不能升级为 exact。"""
    attrs = requirement.preferred_attrs
    candidates = []
    seen_skus = set()

    exact_skus = match_skus(conn, attrs, relaxed)
    if exact_skus:
        placeholders = ",".join("?" for _ in exact_skus)
        rows = conn.execute(
            f"SELECT sku,is_mock,source FROM tools WHERE sku IN ({placeholders}) ORDER BY sku", exact_skus
        ).fetchall()
        for row in rows:
            seen_skus.add(row["sku"])
            candidates.append({
                "candidate_type": "sku", "candidate_id": row["sku"], "tier": "exact",
                "is_mock": bool(row["is_mock"]), "in_stock": True, "differences": [],
                "verification_required": bool(row["is_mock"]), "source": row["source"],
                "tool_attrs": attrs.to_dict(),
            })

    if not relaxed and requirement.diameter_min_mm is not None:
        bases = requirement.allowed_base_materials
        coats = requirement.allowed_coatings
        sql = (
            "SELECT sku,diameter_mm,base_material,coating,is_mock,source FROM tools WHERE category=? "
            "AND diameter_mm BETWEEN ? AND ? AND structure=? AND precision_grade=? AND in_stock=1 "
            f"AND base_material IN ({','.join('?' for _ in bases)}) "
            f"AND coating IN ({','.join('?' for _ in coats)}) ORDER BY ABS(diameter_mm-?),sku LIMIT ?"
        )
        params = [attrs.category, requirement.diameter_min_mm, requirement.diameter_max_mm, attrs.structure,
                  attrs.precision_grade, *bases, *coats, attrs.nominal_diameter_mm, limit]
        for row in conn.execute(sql, params):
            if row["sku"] in seen_skus:
                continue
            differences = []
            if abs(row["diameter_mm"] - attrs.nominal_diameter_mm) > 0.001:
                differences.append(f"刀径 {row['diameter_mm']}mm（首选 {attrs.nominal_diameter_mm}mm）")
            if row["base_material"] != attrs.base_material:
                differences.append(f"基材使用允许备选 {row['base_material']}")
            if row["coating"] != attrs.coating:
                differences.append(f"涂层使用允许备选 {row['coating']}")
            candidates.append({
                "candidate_type": "sku", "candidate_id": row["sku"], "tier": "compatible",
                "is_mock": bool(row["is_mock"]), "in_stock": True, "differences": differences,
                "verification_required": bool(row["is_mock"]), "source": row["source"],
                "tool_attrs": {**attrs.to_dict(), "nominal_diameter_mm": row["diameter_mm"],
                               "base_material": row["base_material"], "coating": row["coating"]},
            })

    catalog_sql = "SELECT * FROM tool_specs WHERE category=?"
    catalog_params = [attrs.category]
    if thread_spec:
        catalog_sql += " AND thread_spec=?"; catalog_params.append(thread_spec)
    elif requirement.diameter_min_mm is not None:
        catalog_sql += " AND diameter_mm BETWEEN ? AND ?"
        catalog_params.extend([requirement.diameter_min_mm, requirement.diameter_max_mm])
    catalog_sql += " ORDER BY diameter_mm,spec_id LIMIT ?"; catalog_params.append(limit)
    for row in conn.execute(catalog_sql, catalog_params):
        if not _catalog_option_allowed(row["base_material"], requirement.allowed_base_materials):
            continue
        if not _catalog_option_allowed(row["coating"], requirement.allowed_coatings):
            continue
        candidates.append({
            "candidate_type": "catalog_spec", "candidate_id": row["spec_id"], "tier": "catalog_only",
            "is_mock": False, "in_stock": None,
            "differences": ["目录未提供库存SKU", "结构或精度字段待供应商确认"],
            "verification_required": True, "source": row["source_id"],
            "catalog_attrs": {"diameter_mm": row["diameter_mm"], "thread_spec": row["thread_spec"],
                              "angle_deg": row["angle_deg"], "base_material": row["base_material"],
                              "coating": row["coating"]},
        })

    tier_order = {"exact": 0, "compatible": 1, "catalog_only": 2}
    candidates.sort(key=lambda c: (tier_order[c["tier"]], c["is_mock"], c["candidate_id"]))
    return candidates[:limit]
