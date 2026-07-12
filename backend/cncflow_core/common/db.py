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
  extra_attrs TEXT,
  is_mock INTEGER DEFAULT 0,
  source TEXT
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

CREATE TABLE IF NOT EXISTS material_sources (
  source_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source_type TEXT NOT NULL,
  locator TEXT,
  license TEXT,
  revision TEXT,
  authority TEXT NOT NULL,
  imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS materials (
  material_code TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  family TEXT NOT NULL,
  grade TEXT,
  condition TEXT,
  density_g_cm3 REAL,
  hardness TEXT,
  machinability_rating INTEGER,
  k_time REAL,
  k_risk REAL,
  tool_wear_cost REAL,
  planning_status TEXT NOT NULL DEFAULT 'unsupported',
  verification_status TEXT NOT NULL DEFAULT 'community_unverified',
  source_id TEXT,
  advisory_json TEXT,
  FOREIGN KEY (source_id) REFERENCES material_sources(source_id)
);

CREATE TABLE IF NOT EXISTS material_aliases (
  alias_normalized TEXT PRIMARY KEY,
  alias TEXT NOT NULL,
  material_code TEXT NOT NULL,
  FOREIGN KEY (material_code) REFERENCES materials(material_code)
);
CREATE INDEX IF NOT EXISTS idx_materials_family ON materials(family, planning_status);

CREATE TABLE IF NOT EXISTS material_price_refs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  material_code TEXT,
  price_per_kg REAL NOT NULL,
  currency TEXT DEFAULT 'CNY',
  region TEXT,
  effective_date TEXT,
  source_id TEXT,
  enabled INTEGER DEFAULT 0,
  FOREIGN KEY (material_code) REFERENCES materials(material_code)
);

CREATE TABLE IF NOT EXISTS tool_specs (
  spec_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  diameter_mm REAL,
  thread_spec TEXT,
  angle_deg REAL,
  structure TEXT,
  base_material TEXT,
  coating TEXT,
  precision_grade TEXT,
  source_id TEXT,
  verification_status TEXT DEFAULT 'catalog_unverified',
  extra_attrs TEXT
);
CREATE INDEX IF NOT EXISTS idx_tool_specs_match ON tool_specs(category, diameter_mm, base_material, coating);

CREATE TABLE IF NOT EXISTS process_cases (
  case_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'draft',
  source_id TEXT,
  feature_type TEXT NOT NULL DEFAULT 'hole',
  material_code TEXT,
  material_family TEXT NOT NULL,
  diameter_mm REAL NOT NULL,
  depth_mm REAL NOT NULL,
  h_over_d REAL NOT NULL,
  hole_type TEXT,
  tolerance_it INTEGER,
  roughness_ra REAL,
  thread_spec TEXT,
  machine_profile_json TEXT,
  planned_chain_json TEXT,
  actual_chain_json TEXT,
  tool_skus_json TEXT,
  actual_params_json TEXT,
  outcome_json TEXT,
  notes TEXT,
  reviewed_by TEXT,
  reviewed_at TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_process_cases_retrieve
  ON process_cases(status, feature_type, material_family, diameter_mm, h_over_d);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  chunk_id TEXT PRIMARY KEY,
  source_id TEXT,
  topic TEXT NOT NULL,
  material_code TEXT,
  tags TEXT,
  content TEXT NOT NULL,
  authority TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES material_sources(source_id)
);

CREATE TABLE IF NOT EXISTS parse_jobs (
  job_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'queued',
  stage TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  options_json TEXT,
  result_json TEXT,
  confirmed_json TEXT,
  plans_json TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  worker_id TEXT,
  started_at TEXT,
  heartbeat_at TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_parse_jobs_queue ON parse_jobs(status, created_at);

CREATE TABLE IF NOT EXISTS uploaded_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  role TEXT NOT NULL,
  original_name TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  detected_type TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(job_id, role),
  FOREIGN KEY (job_id) REFERENCES parse_jobs(job_id)
);

CREATE TABLE IF NOT EXISTS parser_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  message TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (job_id) REFERENCES parse_jobs(job_id)
);

CREATE TABLE IF NOT EXISTS parser_workers (
  worker_id TEXT PRIMARY KEY,
  parser_version TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5("
            "chunk_id UNINDEXED, topic, material_code UNINDEXED, tags, content)"
        )
    except sqlite3.OperationalError:
        # 极简 SQLite 构建可能不含 FTS5；精确标签检索仍可工作。
        pass
    _ensure_column(conn, "tools", "is_mock", "INTEGER DEFAULT 0")
    _ensure_column(conn, "tools", "source", "TEXT")
    # 一期数据库中的无来源刀具全部由 seed_tools.py 生成；迁移后不得冒充真实库存。
    conn.execute(
        "UPDATE tools SET is_mock=1, source='legacy_generated_mock' "
        "WHERE source IS NULL AND extra_attrs IS NULL AND sku LIKE 'SKU-%'"
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    """为旧数据库执行轻量增量迁移，避免破坏已有数据。"""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
