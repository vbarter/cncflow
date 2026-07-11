"""tools 表为空时才灌 mock SKU（部署幂等：不覆盖线上已有刀具数据）。

用法（工作目录 backend/）：python ../deploy/seed_if_empty.py
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from cncflow_core.common.db import get_conn, init_schema
from data.seed_tools import seed

conn = get_conn()
init_schema(conn)
count = conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
if count == 0:
    if os.environ.get("CNCFLOW_SEED_MOCK_TOOLS") == "1":
        print(f"tools 表为空，且已显式启用 mock：灌入 {seed(conn)} 条 mock SKU")
    else:
        print("tools 表为空；生产默认不灌入模拟 SKU（如需演示请设置 CNCFLOW_SEED_MOCK_TOOLS=1）")
else:
    print(f"tools 表已有 {count} 条数据，跳过 seed")
conn.close()
