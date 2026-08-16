"""刀具目录种子：按《刀具SKU目录》灌 TK-001～039，下掉模拟刀。

用法（工作目录 backend/）：python -m data.seed_tools
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cncflow_core.common.db import get_conn, init_schema
from cncflow_core.factory.store import seed_tools_catalog


def seed(conn) -> int:
    init_schema(conn)
    return seed_tools_catalog(conn)


if __name__ == "__main__":
    conn = get_conn()
    count = seed(conn)
    print(f"seeded {count} catalog SKUs")
    conn.close()
