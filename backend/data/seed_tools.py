"""Mock SKU 种子数据生成。

按文档2的 5 项硬性属性字段生成覆盖常用直径×结构×基材×涂层组合的模拟 SKU。
真实刀具库电子表格到位后，替换为 CSV 导入（保持同一 tools 表结构即可）。

刻意留缺口做"部分匹配失败"演示：常用孔径列表不含 14mm——
D14 孔的粗钻直径 13.7 属非标（对齐文档2 §1.4.2 的 Ø13.7 非标钻头示例）。

用法（工作目录 backend/）：python -m data.seed_tools
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cncflow_core.common.db import get_conn, init_schema

# 常用成品孔径（不含 14，见模块注释）
FINISHED_DS = [2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 32, 40, 50, 63, 80]

# 基材×涂层组合（对齐 tool_attrs.yaml 的材料映射所需组合）
COMBOS = [
    ("硬质合金", "无涂层"),
    ("硬质合金", "TiN"),
    ("硬质合金", "TiAlN"),
    ("高速钢", "TiN"),
]

CAT_CODES = {
    "钻头": "DR", "U钻": "UD", "枪钻": "GD", "铰刀": "RM", "镗刀": "BR",
    "丝锥": "TP", "螺纹铣刀": "TM", "平底立铣刀": "FM", "倒角刀": "CH", "中心钻": "SD",
}
ST_CODES = {"标准": "S", "内冷": "C", "枪钻": "G"}
BM_CODES = {"硬质合金": "K", "高速钢": "H"}
CO_CODES = {"无涂层": "N", "TiN": "T", "TiAlN": "A"}
PR_CODES = {"普通": "P", "高精度": "H", "超精密": "U"}


def _rough_d(fd: float) -> float:
    """粗加工刀具直径 = 成品孔径 - 精加工余量（D≤30 留 0.3，D>30 留 0.5）。"""
    return round(fd - 0.3, 2) if fd <= 30 else round(fd - 0.5, 2)


def build_rows() -> list:
    rows = []
    seen = set()

    def add(cat, d, structure, base, coat, prec):
        sku = (
            f"SKU-{CAT_CODES[cat]}-{int(round(d * 100)):05d}-"
            f"{ST_CODES[structure]}{BM_CODES[base]}{CO_CODES[coat]}{PR_CODES[prec]}"
        )
        if sku in seen:
            return
        seen.add(sku)
        rows.append((sku, cat, d, structure, base, coat, prec, 1, None))

    drill_ds = sorted({*FINISHED_DS, *(_rough_d(fd) for fd in FINISHED_DS)})
    u_drill_ds = sorted({fd for fd in FINISHED_DS if fd > 30} | {_rough_d(fd) for fd in FINISHED_DS if fd > 30})
    bore_ds = [fd for fd in FINISHED_DS if fd >= 10]
    ream_ds = [fd for fd in FINISHED_DS if fd <= 63]

    for base, coat in COMBOS:
        for structure in ("标准", "内冷"):
            for d in drill_ds:
                add("钻头", d, structure, base, coat, "普通")
            for d in u_drill_ds:
                add("U钻", d, structure, base, coat, "普通")
            for d in ream_ds:
                for prec in ("高精度", "超精密"):
                    add("铰刀", d, structure, base, coat, prec)
            for d in bore_ds:
                for prec in ("普通", "高精度", "超精密"):
                    add("镗刀", d, structure, base, coat, prec)
            for d in (3, 4, 5, 6, 8, 10, 12, 16):
                add("丝锥", d, structure, base, coat, "普通")
            for d in (8, 10, 12, 16, 20, 25, 30):
                add("螺纹铣刀", d, structure, base, coat, "普通")
            for d in (_rough_d(fd) for fd in FINISHED_DS if fd >= 6):
                add("平底立铣刀", d, structure, base, coat, "普通")
        # 枪钻（结构固定"枪钻"）与直径不限定类刀具
        for d in drill_ds:
            add("枪钻", d, "枪钻", base, coat, "普通")
        for d in (6, 12, 25):
            add("倒角刀", d, "标准", base, coat, "普通")
        for d in (2, 3, 5):
            add("中心钻", d, "标准", base, coat, "普通")

    return rows


def seed(conn) -> int:
    init_schema(conn)
    conn.execute("DELETE FROM tools")
    conn.executemany(
        "INSERT INTO tools (sku, category, diameter_mm, structure, base_material, coating, "
        "precision_grade, in_stock, extra_attrs) VALUES (?,?,?,?,?,?,?,?,?)",
        build_rows(),
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]


if __name__ == "__main__":
    conn = get_conn()
    count = seed(conn)
    print(f"seeded {count} mock SKUs")
    conn.close()
