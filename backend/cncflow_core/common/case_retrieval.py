"""已审核孔加工案例的确定性相似检索。案例只提供证据，不覆盖规则结果。"""
import json
import math
import sqlite3


def _numeric_score(actual, target, scale: float) -> float:
    if actual is None or target is None:
        return 0.0
    return max(0.0, 1.0 - abs(float(actual) - float(target)) / max(abs(float(target)), scale))


def _case_score(row, *, material_code, diameter_mm, h_over_d, hole_type, tolerance_it,
                roughness_ra, thread_spec) -> tuple[float, list]:
    weighted = []
    differences = []

    def add(weight, score, label=None):
        weighted.append((weight, score))
        if label and score < 0.999:
            differences.append(label)

    if row["material_code"] and material_code:
        add(0.22, 1.0 if row["material_code"] == material_code else 0.0, "材料牌号不同")
    else:
        add(0.14, 1.0)  # 已由材料族硬过滤
    add(0.22, _numeric_score(row["diameter_mm"], diameter_mm, 1.0), "孔径不同")
    add(0.20, _numeric_score(row["h_over_d"], h_over_d, 1.0), "深径比不同")
    if row["tolerance_it"] is not None and tolerance_it is not None:
        add(0.14, max(0.0, 1.0 - abs(row["tolerance_it"] - tolerance_it) / 6.0), "IT等级不同")
    if row["hole_type"] and hole_type:
        add(0.08, 1.0 if row["hole_type"] == hole_type else 0.0, "孔型不同")
    if row["roughness_ra"] is not None and roughness_ra is not None:
        add(0.08, _numeric_score(row["roughness_ra"], roughness_ra, 0.4), "粗糙度不同")
    if row["thread_spec"] or thread_spec:
        add(0.06, 1.0 if (row["thread_spec"] or "") == (thread_spec or "") else 0.0, "螺纹不同")

    total_weight = sum(w for w, _ in weighted) or 1.0
    return round(sum(w * s for w, s in weighted) / total_weight, 3), differences


def retrieve_process_cases(conn: sqlite3.Connection, *, material_code: str, material_family: str,
                           diameter_mm: float, depth_mm: float, hole_type: str,
                           tolerance_it: int, roughness_ra=None, thread_spec=None,
                           limit: int = 5, min_score: float = 0.35) -> list:
    rows = conn.execute(
        "SELECT * FROM process_cases WHERE status='verified' AND feature_type='hole' "
        "AND material_family=? AND diameter_mm BETWEEN ? AND ? ORDER BY created_at DESC LIMIT 100",
        (material_family, max(0.0, diameter_mm * 0.4), diameter_mm * 1.6),
    ).fetchall()
    h_over_d = depth_mm / diameter_mm
    ranked = []
    for row in rows:
        score, differences = _case_score(
            row, material_code=material_code, diameter_mm=diameter_mm, h_over_d=h_over_d,
            hole_type=hole_type, tolerance_it=tolerance_it, roughness_ra=roughness_ra,
            thread_spec=thread_spec,
        )
        if score < min_score:
            continue
        ranked.append({
            "case_id": row["case_id"], "similarity": score, "differences": differences,
            "material_code": row["material_code"], "diameter_mm": row["diameter_mm"],
            "h_over_d": row["h_over_d"], "tolerance_it": row["tolerance_it"],
            "actual_chain": json.loads(row["actual_chain_json"] or "[]"),
            "actual_params": json.loads(row["actual_params_json"] or "{}"),
            "outcome": json.loads(row["outcome_json"] or "{}"),
            "notes": row["notes"], "source_id": row["source_id"],
        })
    ranked.sort(key=lambda item: (-item["similarity"], item["case_id"]))
    return ranked[:limit]


def insert_process_case(conn: sqlite3.Connection, case: dict) -> None:
    """供受控导入脚本和测试使用；线上不暴露无鉴权写 API。"""
    diameter = float(case["diameter_mm"])
    depth = float(case["depth_mm"])
    if diameter <= 0 or depth <= 0:
        raise ValueError("案例孔径和孔深必须为正数")
    status = case.get("status", "draft")
    if status not in {"draft", "verified", "rejected"}:
        raise ValueError("案例状态须为 draft/verified/rejected")
    conn.execute(
        "INSERT INTO process_cases(case_id,status,source_id,feature_type,material_code,material_family,"
        "diameter_mm,depth_mm,h_over_d,hole_type,tolerance_it,roughness_ra,thread_spec,machine_profile_json,"
        "planned_chain_json,actual_chain_json,tool_skus_json,actual_params_json,outcome_json,notes,reviewed_by,reviewed_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (case["case_id"], status, case.get("source_id"), "hole", case.get("material_code"),
         case["material_family"], diameter, depth, depth / diameter, case.get("hole_type", "through"),
         case.get("tolerance_it"), case.get("roughness_ra"), case.get("thread_spec"),
         json.dumps(case.get("machine_profile", {}), ensure_ascii=False),
         json.dumps(case.get("planned_chain", []), ensure_ascii=False),
         json.dumps(case.get("actual_chain", []), ensure_ascii=False),
         json.dumps(case.get("tool_skus", []), ensure_ascii=False),
         json.dumps(case.get("actual_params", {}), ensure_ascii=False),
         json.dumps(case.get("outcome", {}), ensure_ascii=False), case.get("notes"),
         case.get("reviewed_by"), case.get("reviewed_at")),
    )
    if status == "verified" and case.get("notes"):
        chunk_id = f"case:{case['case_id']}"
        content = case["notes"]
        conn.execute(
            "INSERT INTO knowledge_chunks(chunk_id,source_id,topic,material_code,tags,content,authority) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET content=excluded.content,tags=excluded.tags",
            (chunk_id, case.get("source_id"), "verified_process_case", case.get("material_code"),
             f"hole {case['material_family']} D{diameter:g}", content, "verified_case"),
        )
        try:
            conn.execute("DELETE FROM knowledge_chunks_fts WHERE chunk_id=?", (chunk_id,))
            conn.execute(
                "INSERT INTO knowledge_chunks_fts(chunk_id,topic,material_code,tags,content) VALUES(?,?,?,?,?)",
                (chunk_id, "verified_process_case", case.get("material_code"),
                 f"hole {case['material_family']} D{diameter:g}", content),
            )
        except sqlite3.OperationalError:
            pass
    conn.commit()
