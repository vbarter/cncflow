"""SQLite 连接与 schema。数据文件默认在 backend/data/cncflow.db。"""
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cncflow.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tools (
  sku TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  diameter_mm REAL NOT NULL,
  structure TEXT NOT NULL,
  base_material TEXT NOT NULL,
  coating TEXT NOT NULL,
  precision_grade TEXT NOT NULL,
  in_stock INTEGER DEFAULT 1,
  extra_attrs TEXT
);
CREATE INDEX IF NOT EXISTS idx_tools_match
  ON tools (category, diameter_mm, structure, base_material, coating, precision_grade);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_json TEXT,
  machinability_level INTEGER,
  fired_rules TEXT,
  response_json TEXT,
  rules_version TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
"""


def get_conn(db_path=None) -> sqlite3.Connection:
    if str(db_path) == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        path = Path(db_path) if db_path else DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
