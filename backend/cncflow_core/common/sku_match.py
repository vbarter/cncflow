"""SKU 全等匹配（文档2第三步）：5 项硬性属性全部达标才保留，任一不达标剔除。

倒角刀/中心钻直径"不限定，按孔口规格选型"→ relaxed 模式放宽直径与精度，只匹配
大类 + 基材 + 涂层。
"""
import sqlite3

from .models import ToolAttrs


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
