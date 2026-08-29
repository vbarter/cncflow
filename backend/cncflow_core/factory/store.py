"""工厂配置读写。"""
import json

from .defaults import (
    MACHINE_SEEDS, MATERIAL_ALIASES, MATERIAL_PRICES, RATE_TABLE,
    TOOL_SEEDS, TOOL_TYPE_CATEGORY,
)


def _opt_float(value):
    if value is None or value == "":
        return None
    return float(value)



_OBSOLETE_MACHINE_IDS = (
    "VM-3AX", "VM-4AX", "VM-5AX", "HMC-1",
    "GANTRY-1", "JIG-1", "EDM-1", "WEDM-1", "LATHE-1", "MT-1", "ODGR-1", "SURFGR-1",
)
_MACHINE_COLS = (
    "id", "type", "axes", "travel_x", "travel_y", "travel_z",
    "max_rpm", "power_kw", "tool_change_s", "fixture_mode",
    "hourly_rate", "setup_fee", "enabled",
)
_MATERIAL_COLS = (
    "material_code", "price_per_kg", "scrap_price_per_kg", "density_g_cm3",
    "family", "display_name", "recycle_rate", "warning", "enabled",
)


def _machine_extra(item: dict) -> dict:
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    for key, value in item.items():
        if key in _MACHINE_COLS or key in {"extra", "extra_json", "enabled"}:
            continue
        extra[key] = value
    return extra


def _upsert_seed_machine(conn, machine: dict) -> None:
    extra = json.dumps(_machine_extra(machine), ensure_ascii=False)
    conn.execute(
        "INSERT OR IGNORE INTO machines (id, type, axes, travel_x, travel_y, travel_z, max_rpm, power_kw, "
        "tool_change_s, fixture_mode, hourly_rate, setup_fee, extra_json, enabled) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            machine["id"], machine["type"], machine.get("axes"),
            machine.get("travel_x"), machine.get("travel_y"), machine.get("travel_z"),
            machine.get("max_rpm"), machine.get("power_kw"), machine.get("tool_change_s"),
            machine.get("fixture_mode"), machine.get("hourly_rate"), machine.get("setup_fee"),
            extra, 1 if machine.get("enabled", True) else 0,
        ),
    )


def _public_machine(row) -> dict:
    item = dict(row)
    raw = item.pop("extra_json", None)
    if raw:
        try:
            item.update(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            pass
    return item


def _material_extra(item: dict) -> dict:
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    for key in ("tier", "alias_of"):
        if item.get(key) is not None:
            extra[key] = item[key]
    return extra


def _public_material(row) -> dict:
    item = dict(row)
    raw = item.pop("extra_json", None)
    if raw:
        try:
            item.update(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            pass
    return item


def _public_rate(row) -> dict:
    item = dict(row)
    item.pop("programming_fee_new", None)
    return item


def _tool_extra(item: dict) -> dict:
    extra = {}
    raw = item.get("extra_attrs")
    if isinstance(raw, str) and raw:
        try:
            extra.update(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            pass
    if isinstance(item.get("extra"), dict):
        extra.update(item["extra"])
    for key in ("tool_type", "spec", "r", "flutes", "max_ld"):
        if item.get(key) is not None:
            extra[key] = item[key]
    return extra


def _public_tool(row) -> dict:
    item = dict(row)
    raw = item.pop("extra_attrs", None)
    extra = {}
    if raw:
        try:
            extra = json.loads(raw) or {}
        except (TypeError, json.JSONDecodeError):
            extra = {}
    item.update(extra)
    if not item.get("tool_type"):
        item["tool_type"] = item.get("category")
    return item


def _upsert_seed_material(conn, row: dict) -> None:
    extra = json.dumps(_material_extra(row), ensure_ascii=False)
    conn.execute(
        "INSERT OR IGNORE INTO factory_material_prices "
        "(material_code, price_per_kg, scrap_price_per_kg, density_g_cm3, family, "
        "display_name, recycle_rate, warning, extra_json, enabled) "
        "VALUES (?,?,?,?,?,?,?,?,?,1)",
        (
            row["material_code"], row["price_per_kg"], row.get("scrap_price_per_kg", 0),
            row.get("density_g_cm3"), row.get("family"), row.get("display_name"),
            row.get("recycle_rate"), row.get("warning"), extra,
        ),
    )
    conn.execute(
        "UPDATE factory_material_prices SET "
        "density_g_cm3=COALESCE(density_g_cm3, ?), family=COALESCE(family, ?), "
        "display_name=COALESCE(display_name, ?), recycle_rate=COALESCE(recycle_rate, ?), "
        "warning=COALESCE(warning, ?), extra_json=? "
        "WHERE material_code=? AND (extra_json IS NULL OR extra_json='{}' OR extra_json NOT LIKE '%tier%')",
        (
            row.get("density_g_cm3"), row.get("family"), row.get("display_name"),
            row.get("recycle_rate"), row.get("warning"), extra, row["material_code"],
        ),
    )


def _upsert_material_aliases(conn) -> None:
    by_code = {r["material_code"]: r for r in MATERIAL_PRICES}
    for alias, target in MATERIAL_ALIASES.items():
        src = by_code.get(target)
        if not src:
            continue
        row = {
            **src,
            "material_code": alias,
            "display_name": src.get("display_name") or target,
            "tier": "alias",
            "alias_of": target,
            "warning": None,
        }
        extra = json.dumps({"tier": "alias", "alias_of": target}, ensure_ascii=False)
        conn.execute(
            "INSERT INTO factory_material_prices "
            "(material_code, price_per_kg, scrap_price_per_kg, density_g_cm3, family, "
            "display_name, recycle_rate, warning, extra_json, enabled) "
            "VALUES (?,?,?,?,?,?,?,?,?,1) "
            "ON CONFLICT(material_code) DO UPDATE SET "
            "price_per_kg=excluded.price_per_kg, scrap_price_per_kg=excluded.scrap_price_per_kg, "
            "density_g_cm3=excluded.density_g_cm3, family=excluded.family, "
            "display_name=excluded.display_name, recycle_rate=excluded.recycle_rate, "
            "extra_json=excluded.extra_json",
            (
                alias, src["price_per_kg"], src.get("scrap_price_per_kg", 0),
                src.get("density_g_cm3"), src.get("family"), row["display_name"],
                src.get("recycle_rate"), None, extra,
            ),
        )


def _upsert_seed_tool(conn, tool: dict) -> None:
    extra = json.dumps(_tool_extra(tool), ensure_ascii=False)
    conn.execute(
        "INSERT OR IGNORE INTO tools (sku, category, diameter_mm, structure, base_material, coating, "
        "precision_grade, in_stock, extra_attrs, is_mock, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,0,'sku_catalog')",
        (
            tool["sku"], tool["category"], float(tool.get("diameter_mm") or 0),
            tool.get("structure") or "标准", tool.get("base_material") or "硬质合金",
            tool.get("coating") or "无涂层", tool.get("precision_grade") or "普通",
            1 if tool.get("in_stock", True) else 0, extra,
        ),
    )


def seed_tools_catalog(conn) -> int:
    """下掉模拟刀，灌 TK-001～039。用户在工厂页加的刀（factory_ui）保留。"""
    conn.execute(
        "DELETE FROM tools WHERE is_mock=1 OR IFNULL(source,'') IN "
        "('generated_mock','legacy_generated_mock')"
    )
    for tool in TOOL_SEEDS:
        _upsert_seed_tool(conn, tool)
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]


def seed_factory(conn) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO factory_settings (id, profit_pct, floor_charge, inspect_fee, "
        "ignore_available_machines, batch_size, blank_type) VALUES (1, 15, 0, 60, 0, 1, '板料')"
    )
    conn.executemany(
        "INSERT INTO rate_table (equipment_type, hourly_rate, setup_fee, programming_hourly_rate) "
        "VALUES (:equipment_type, :hourly_rate, :setup_fee, :programming_hourly_rate) "
        "ON CONFLICT(equipment_type) DO UPDATE SET programming_hourly_rate="
        "COALESCE(rate_table.programming_hourly_rate, excluded.programming_hourly_rate)",
        RATE_TABLE,
    )
    conn.execute(
        "DELETE FROM machines WHERE id IN ({})".format(
            ",".join("?" * len(_OBSOLETE_MACHINE_IDS))
        ),
        _OBSOLETE_MACHINE_IDS,
    )
    for machine in MACHINE_SEEDS:
        _upsert_seed_machine(conn, machine)
    for row in MATERIAL_PRICES:
        _upsert_seed_material(conn, row)
    _upsert_material_aliases(conn)
    seed_tools_catalog(conn)
    conn.commit()


def resolve_material_code(code: str | None) -> str | None:
    if not code:
        return code
    return MATERIAL_ALIASES.get(code, code)


def _row(r):
    return dict(r) if r is not None else None


def get_config(conn) -> dict:
    seed_factory(conn)
    settings = _row(conn.execute("SELECT * FROM factory_settings WHERE id=1").fetchone())
    settings["ignore_available_machines"] = bool(settings["ignore_available_machines"])
    extra = settings.pop("extra_json", None)
    settings["extra"] = json.loads(extra) if extra else {}
    return {
        "settings": settings,
        "machines": [_public_machine(r) for r in conn.execute("SELECT * FROM machines ORDER BY id")],
        "tools": [_public_tool(r) for r in conn.execute("SELECT * FROM tools ORDER BY sku")],
        "material_prices": [
            _public_material(r)
            for r in conn.execute("SELECT * FROM factory_material_prices ORDER BY material_code")
        ],
        "rate_table": [
            _public_rate(r)
            for r in conn.execute("SELECT * FROM rate_table ORDER BY equipment_type")
        ],
    }


def put_config(conn, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("请求体须为 JSON 对象")
    settings = payload.get("settings") or {}
    extra = settings.get("extra") if isinstance(settings.get("extra"), dict) else {}
    conn.execute(
        "INSERT INTO factory_settings (id, profit_pct, floor_charge, inspect_fee, "
        "ignore_available_machines, batch_size, blank_type, extra_json) VALUES (1,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET profit_pct=excluded.profit_pct, floor_charge=excluded.floor_charge, "
        "inspect_fee=excluded.inspect_fee, ignore_available_machines=excluded.ignore_available_machines, "
        "batch_size=excluded.batch_size, blank_type=excluded.blank_type, extra_json=excluded.extra_json",
        (
            float(settings.get("profit_pct", 15)),
            float(settings.get("floor_charge", 0)),
            float(settings.get("inspect_fee", 60)),
            1 if settings.get("ignore_available_machines") else 0,
            int(settings.get("batch_size", 1)),
            settings.get("blank_type") or "板料",
            json.dumps(extra, ensure_ascii=False),
        ),
    )
    if "machines" in payload:
        if not isinstance(payload["machines"], list):
            raise ValueError("machines 须为数组")
        conn.execute("DELETE FROM machines")
        for item in payload["machines"]:
            extra = json.dumps(_machine_extra(item), ensure_ascii=False)
            conn.execute(
                "INSERT INTO machines (id, type, axes, travel_x, travel_y, travel_z, max_rpm, power_kw, "
                "tool_change_s, fixture_mode, hourly_rate, setup_fee, extra_json, enabled) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item["id"], item.get("type") or item.get("equipment_type"),
                    item.get("axes"), item.get("travel_x"), item.get("travel_y"), item.get("travel_z"),
                    item.get("max_rpm"), item.get("power_kw"), item.get("tool_change_s"),
                    item.get("fixture_mode"), item.get("hourly_rate"), item.get("setup_fee"),
                    extra, 1 if item.get("enabled", True) else 0,
                ),
            )
    if "tools" in payload:
        if not isinstance(payload["tools"], list):
            raise ValueError("tools 须为数组")
        keep = []
        for item in payload["tools"]:
            sku = item["sku"]
            keep.append(sku)
            tool_type = item.get("tool_type") or item.get("category") or "钻头"
            category = item.get("category") or TOOL_TYPE_CATEGORY.get(tool_type) or tool_type
            extra = json.dumps(_tool_extra({**item, "tool_type": tool_type}), ensure_ascii=False)
            conn.execute(
                "INSERT INTO tools (sku, category, diameter_mm, structure, base_material, coating, "
                "precision_grade, in_stock, extra_attrs, is_mock, source) "
                "VALUES (?,?,?,?,?,?,?,?,?,0,'factory_ui') "
                "ON CONFLICT(sku) DO UPDATE SET "
                "category=excluded.category, diameter_mm=excluded.diameter_mm, "
                "structure=excluded.structure, base_material=excluded.base_material, "
                "coating=excluded.coating, precision_grade=excluded.precision_grade, "
                "in_stock=excluded.in_stock, extra_attrs=excluded.extra_attrs, is_mock=0",
                (
                    sku,
                    category,
                    float(item["diameter_mm"]) if item.get("diameter_mm") is not None else 0.0,
                    item.get("structure") or "标准",
                    item.get("base_material") or "硬质合金",
                    item.get("coating") or "无涂层",
                    item.get("precision_grade") or "普通",
                    1 if item.get("in_stock", True) else 0,
                    extra,
                ),
            )
        if keep:
            conn.execute(
                f"DELETE FROM tools WHERE sku NOT IN ({','.join('?' * len(keep))})",
                keep,
            )
        else:
            conn.execute("DELETE FROM tools")
    if "material_prices" in payload:
        if not isinstance(payload["material_prices"], list):
            raise ValueError("material_prices 须为数组")
        conn.execute("DELETE FROM factory_material_prices")
        for item in payload["material_prices"]:
            extra = json.dumps(_material_extra(item), ensure_ascii=False)
            conn.execute(
                "INSERT INTO factory_material_prices "
                "(material_code, price_per_kg, scrap_price_per_kg, density_g_cm3, family, "
                "display_name, recycle_rate, warning, extra_json, enabled) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    item["material_code"], float(item["price_per_kg"]),
                    float(item.get("scrap_price_per_kg", 0)),
                    _opt_float(item.get("density_g_cm3")),
                    item.get("family") or None,
                    item.get("display_name") or None,
                    _opt_float(item.get("recycle_rate")),
                    item.get("warning") or None,
                    extra,
                    1 if item.get("enabled", True) else 0,
                ),
            )
        _upsert_material_aliases(conn)
    if "rate_table" in payload:
        if not isinstance(payload["rate_table"], list):
            raise ValueError("rate_table 须为数组")
        for item in payload["rate_table"]:
            conn.execute(
                "INSERT INTO rate_table (equipment_type, hourly_rate, setup_fee, programming_hourly_rate) "
                "VALUES (?,?,?,?) ON CONFLICT(equipment_type) DO UPDATE SET "
                "hourly_rate=excluded.hourly_rate, setup_fee=excluded.setup_fee, "
                "programming_hourly_rate=excluded.programming_hourly_rate",
                (
                    item["equipment_type"], float(item["hourly_rate"]),
                    float(item.get("setup_fee", 0)), _opt_float(item.get("programming_hourly_rate")),
                ),
            )
    conn.commit()
    return get_config(conn)
