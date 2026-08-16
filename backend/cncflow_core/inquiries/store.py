"""询价单 / 零件仓储与状态汇总。"""
import json
import uuid

UI = {
    "draft": "pending", "parse_failed": "pending", "need_params": "pending",
    "parsing": "quoting", "quoting": "quoting", "revising": "quoting",
    "quoted": "review", "confirmed": "done", "abandoned": "abandoned",
}


def rollup(statuses):
    if not statuses:
        return "pending"
    if all(s == "confirmed" for s in statuses):
        return "done"
    if any(s in {"parsing", "quoting", "revising"} for s in statuses):
        return "quoting"
    if any(s == "quoted" for s in statuses) and not all(s in {"quoted", "confirmed", "abandoned"} for s in statuses):
        return "review"
    if any(s == "quoted" for s in statuses):
        return "review"
    return "pending"


def _part(row):
    item = dict(row)
    item["is_repeat_order"] = bool(item.get("is_repeat_order"))
    item["quote"] = json.loads(item.pop("quote_json") or "null")
    item["ui_status"] = UI.get(item["status"], "pending")
    return item


def create_inquiry(conn, payload: dict) -> dict:
    iid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO inquiries (id,title,customer,project,due_date) VALUES (?,?,?,?,?)",
        (iid, payload.get("title") or "", payload.get("customer") or "",
         payload.get("project") or "", payload.get("due_date") or ""),
    )
    conn.commit()
    return get_inquiry(conn, iid)


def list_inquiries(conn, ui_status=None, customer=None, project=None):
    rows = conn.execute("SELECT * FROM inquiries ORDER BY created_at DESC").fetchall()
    items = []
    for row in rows:
        inquiry = dict(row)
        parts = [_part(r) for r in conn.execute("SELECT * FROM parts WHERE inquiry_id=?", (inquiry["id"],))]
        inquiry["parts"] = parts
        inquiry["ui_status"] = rollup([p["status"] for p in parts])
        inquiry["amount"] = sum((p.get("quote") or {}).get("quote", {}).get("amount") or 0 for p in parts)
        if ui_status and inquiry["ui_status"] != ui_status:
            continue
        if customer and customer not in (inquiry.get("customer") or ""):
            continue
        if project and project not in (inquiry.get("project") or ""):
            continue
        items.append(inquiry)
    return items


def get_inquiry(conn, iid: str) -> dict:
    row = conn.execute("SELECT * FROM inquiries WHERE id=?", (iid,)).fetchone()
    if row is None:
        raise KeyError(iid)
    inquiry = dict(row)
    inquiry["parts"] = [_part(r) for r in conn.execute("SELECT * FROM parts WHERE inquiry_id=?", (iid,))]
    inquiry["ui_status"] = rollup([p["status"] for p in inquiry["parts"]])
    return inquiry


def add_part(conn, iid: str, payload: dict) -> dict:
    get_inquiry(conn, iid)
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO parts (id,inquiry_id,name,qty,material_code,surface_finish,tolerance_it,roughness_ra,"
        "batch_size,is_repeat_order,blank_type,length,width,height,diameter,status,slider) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            pid, iid, payload.get("name") or "零件",
            int(payload.get("qty") or 1), payload.get("material") or payload.get("material_code") or "铝合金",
            payload.get("surface_finish") or "", payload.get("tolerance_it"), payload.get("roughness_ra"),
            int(payload.get("batch_size") or payload.get("qty") or 1),
            1 if payload.get("is_repeat_order") else 0,
            payload.get("blank_type") or "板料",
            payload.get("length"), payload.get("width"), payload.get("height"), payload.get("diameter"),
            "draft", payload.get("slider") or "标准",
        ),
    )
    conn.commit()
    return get_part(conn, pid)


def get_part(conn, pid: str) -> dict:
    row = conn.execute("SELECT * FROM parts WHERE id=?", (pid,)).fetchone()
    if row is None:
        raise KeyError(pid)
    return _part(row)


def update_part(conn, pid: str, patch: dict) -> dict:
    part = get_part(conn, pid)
    if part["status"] == "confirmed":
        raise PermissionError("confirmed")
    allowed = {"name", "qty", "material_code", "surface_finish", "tolerance_it", "roughness_ra",
               "batch_size", "is_repeat_order", "blank_type", "length", "width", "height", "diameter", "slider"}
    if "material" in patch:
        patch = {**patch, "material_code": patch["material"]}
    sets, vals = [], []
    for key in allowed:
        if key in patch:
            val = patch[key]
            if key == "is_repeat_order":
                val = 1 if val else 0
            sets.append(f"{key}=?")
            vals.append(val)
    if part["status"] == "quoted" and sets:
        sets.append("status=?")
        vals.append("revising")
    if sets:
        vals.append(pid)
        conn.execute(f"UPDATE parts SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?", vals)
        conn.commit()
    return get_part(conn, pid)


def set_quote(conn, pid: str, quote: dict, status="quoted") -> dict:
    conn.execute(
        "UPDATE parts SET quote_json=?, status=?, updated_at=datetime('now') WHERE id=?",
        (json.dumps(quote, ensure_ascii=False), status, pid),
    )
    conn.commit()
    return get_part(conn, pid)


def set_status(conn, pid: str, status: str) -> dict:
    conn.execute("UPDATE parts SET status=?, updated_at=datetime('now') WHERE id=?", (status, pid))
    conn.commit()
    return get_part(conn, pid)
