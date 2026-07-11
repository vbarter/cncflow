"""从受控 JSON 文件幂等导入孔加工案例；不提供公网写接口。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cncflow_core.common.case_retrieval import insert_process_case
from cncflow_core.common.db import get_conn, init_schema
from cncflow_core.common.materials import seed_material_catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="JSON数组文件")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    items = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("输入文件顶层必须是 JSON 数组")
    conn = get_conn(args.db)
    init_schema(conn)
    seed_material_catalog(conn)
    imported = 0
    for item in items:
        conn.execute("DELETE FROM process_cases WHERE case_id=?", (item["case_id"],))
        insert_process_case(conn, item)
        imported += 1
    conn.close()
    print(f"imported {imported} process cases")


if __name__ == "__main__":
    main()
