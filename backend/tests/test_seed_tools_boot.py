"""空库启动要灌入 mock SKU，现网才能选出工步刀具。"""
from cncflow_core.common.db import get_conn
from app import create_app


def test_create_app_seeds_tools_when_empty(tmp_path):
    db = tmp_path / "empty.db"
    create_app(db_path=str(db))
    conn = get_conn(str(db))
    n = conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
    conn.close()
    assert n > 0
