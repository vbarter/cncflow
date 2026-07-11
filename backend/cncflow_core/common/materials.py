"""统一材料目录：规范化用户输入，隔离已验证规则与社区参考知识。"""
from dataclasses import dataclass
import json
import re
import sqlite3
from typing import Optional

from .rule_loader import load_rules


def normalize_alias(value: str) -> str:
    return re.sub(r"[\s_\-#（）()]+", "", str(value)).lower()


@dataclass(frozen=True)
class MaterialProfile:
    material_code: str
    canonical_name: str
    family: str
    grade: Optional[str]
    condition: Optional[str]
    density_g_cm3: Optional[float]
    hardness: Optional[str]
    machinability_rating: Optional[int]
    planning_status: str
    verification_status: str
    source_id: Optional[str]
    advisory: dict

    @property
    def planning_enabled(self) -> bool:
        return self.planning_status.startswith("enabled")

    def to_dict(self) -> dict:
        return {
            "material_code": self.material_code,
            "canonical_name": self.canonical_name,
            "family": self.family,
            "grade": self.grade,
            "condition": self.condition,
            "density_g_cm3": self.density_g_cm3,
            "hardness": self.hardness,
            "machinability_rating": self.machinability_rating,
            "planning_status": self.planning_status,
            "verification_status": self.verification_status,
            "source_id": self.source_id,
            "advisory": self.advisory,
        }


def seed_material_catalog(conn: sqlite3.Connection) -> None:
    rules = load_rules("common/materials.yaml")
    for source_id, source in rules["sources"].items():
        conn.execute(
            "INSERT INTO material_sources(source_id,title,source_type,locator,license,revision,authority) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET title=excluded.title, "
            "locator=excluded.locator, license=excluded.license, revision=excluded.revision, authority=excluded.authority",
            (source_id, source["title"], source["source_type"], source.get("locator"), source.get("license"),
             source.get("revision"), source["authority"]),
        )

    for item in rules["materials"]:
        advisory = json.dumps(item.get("advisory", {}), ensure_ascii=False)
        conn.execute(
            "INSERT INTO materials(material_code,canonical_name,family,grade,condition,density_g_cm3,hardness,"
            "machinability_rating,k_time,k_risk,tool_wear_cost,planning_status,verification_status,source_id,advisory_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(material_code) DO UPDATE SET "
            "canonical_name=excluded.canonical_name,family=excluded.family,grade=excluded.grade,condition=excluded.condition,"
            "density_g_cm3=excluded.density_g_cm3,hardness=excluded.hardness,machinability_rating=excluded.machinability_rating,"
            "k_time=excluded.k_time,k_risk=excluded.k_risk,tool_wear_cost=excluded.tool_wear_cost,"
            "planning_status=excluded.planning_status,verification_status=excluded.verification_status,"
            "source_id=excluded.source_id,advisory_json=excluded.advisory_json",
            (item["code"], item["name"], item["family"], item.get("grade"), item.get("condition"),
             item.get("density"), item.get("hardness"), item.get("machinability_rating"), item.get("k_time"),
             item.get("k_risk"), item.get("tool_wear_cost"), item["planning_status"],
             item["verification_status"], item["source_id"], advisory),
        )
        aliases = {item["code"], item["name"], *item.get("aliases", [])}
        for alias in aliases:
            conn.execute(
                "INSERT INTO material_aliases(alias_normalized,alias,material_code) VALUES(?,?,?) "
                "ON CONFLICT(alias_normalized) DO UPDATE SET alias=excluded.alias,material_code=excluded.material_code",
                (normalize_alias(alias), alias, item["code"]),
            )
        summary = item.get("advisory", {}).get("summary")
        if summary:
            chunk_id = f"material:{item['code']}:summary"
            conn.execute(
                "INSERT INTO knowledge_chunks(chunk_id,source_id,topic,material_code,tags,content,authority) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET content=excluded.content,tags=excluded.tags",
                (chunk_id, item["source_id"], "material_advisory", item["code"],
                 f"{item['family']} {item.get('grade','')} 工艺建议", summary, item["verification_status"]),
            )
            try:
                conn.execute("DELETE FROM knowledge_chunks_fts WHERE chunk_id=?", (chunk_id,))
                conn.execute(
                    "INSERT INTO knowledge_chunks_fts(chunk_id,topic,material_code,tags,content) VALUES(?,?,?,?,?)",
                    (chunk_id, "material_advisory", item["code"],
                     f"{item['family']} {item.get('grade','')} 工艺建议", summary),
                )
            except sqlite3.OperationalError:
                pass
    conn.commit()


def _row_to_profile(row) -> MaterialProfile:
    return MaterialProfile(
        material_code=row["material_code"], canonical_name=row["canonical_name"], family=row["family"],
        grade=row["grade"], condition=row["condition"], density_g_cm3=row["density_g_cm3"],
        hardness=row["hardness"], machinability_rating=row["machinability_rating"],
        planning_status=row["planning_status"], verification_status=row["verification_status"],
        source_id=row["source_id"], advisory=json.loads(row["advisory_json"] or "{}"),
    )


def resolve_material(conn: sqlite3.Connection, value: str) -> MaterialProfile:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("material 或 material_code 必填")
    normalized = normalize_alias(value)
    row = conn.execute(
        "SELECT m.* FROM material_aliases a JOIN materials m ON m.material_code=a.material_code "
        "WHERE a.alias_normalized=?", (normalized,),
    ).fetchone()
    if row is None:
        raise ValueError(f"material 无法识别: {value!r}；请使用材料目录中的标准名称、牌号或别名")
    return _row_to_profile(row)


def list_materials(conn: sqlite3.Connection, family=None, planning_status=None, query=None) -> list:
    sql = "SELECT * FROM materials WHERE 1=1"
    params = []
    if family:
        sql += " AND family=?"; params.append(family)
    if planning_status:
        sql += " AND planning_status=?"; params.append(planning_status)
    if query:
        sql += " AND (canonical_name LIKE ? OR material_code LIKE ? OR grade LIKE ?)"
        params.extend([f"%{query}%"] * 3)
    sql += " ORDER BY family, material_code"
    return [_row_to_profile(r).to_dict() for r in conn.execute(sql, params)]


def material_evidence(conn: sqlite3.Connection, material_code: str) -> list:
    rows = conn.execute(
        "SELECT chunk_id,source_id,topic,content,authority FROM knowledge_chunks WHERE material_code=? ORDER BY chunk_id",
        (material_code,),
    ).fetchall()
    return [dict(row) for row in rows]


def search_knowledge(conn: sqlite3.Connection, query: str, material_code: str = None, limit: int = 10) -> list:
    """本地全文检索；FTS5 不可用时降级为 LIKE。"""
    if not query or not query.strip():
        return []
    try:
        sql = (
            "SELECT k.chunk_id,k.source_id,k.topic,k.material_code,k.content,k.authority,bm25(knowledge_chunks_fts) rank "
            "FROM knowledge_chunks_fts JOIN knowledge_chunks k USING(chunk_id) WHERE knowledge_chunks_fts MATCH ?"
        )
        params = [query]
        if material_code:
            sql += " AND k.material_code=?"; params.append(material_code)
        sql += " ORDER BY rank LIMIT ?"; params.append(limit)
        results = [dict(row) for row in conn.execute(sql, params)]
        if results:
            return results
    except sqlite3.OperationalError:
        pass
    # 中文连续文本在默认 unicode61 tokenizer 下可能无法按短语切分，空结果时也使用 LIKE。
    sql = "SELECT chunk_id,source_id,topic,material_code,content,authority FROM knowledge_chunks WHERE content LIKE ?"
    params = [f"%{query}%"]
    if material_code:
        sql += " AND material_code=?"; params.append(material_code)
    sql += " ORDER BY chunk_id LIMIT ?"; params.append(limit)
    return [dict(row) for row in conn.execute(sql, params)]
