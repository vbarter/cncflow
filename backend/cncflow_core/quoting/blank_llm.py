"""独立毛坯 LLM：只识别类型和零件包络，余量/库存仍由 blank.decide 决定。"""
from __future__ import annotations

import hashlib
import json
import math
import os

from ..geometry import llm as geometry_llm
from . import blank


BLANK_MODEL_DEFAULT = "gpt-6-astra"
MAX_STEP_CHARS_DEFAULT = 800_000
_LABELS = {
    "plate": "板料",
    "square_bar": "方料",
    "round_bar": "圆棒",
}

SYSTEM_PROMPT = """你是 CNC 毛坯投影识别器。根据 STEP 文本和可选几何包络，只返回一个 JSON 对象：
{"blank_type":"plate|square_bar|round_bar","envelope_mm":{...},"rationale":"一句短理由"}

约束：
- blank_type 只能是 plate、square_bar、round_bar。
- plate/square_bar 的 envelope_mm 只能含 length、width、height（mm）。
- round_bar 的 envelope_mm 只能含 diameter、length（mm）。
- 只报告零件投影/包络，不增加加工余量。
- 禁止输出标准库存尺寸、材料单价、加工价格或任何报价。
- STEP 是主依据；已解析 bbox 只用于校验投影。
"""


def blank_model() -> str:
    return os.environ.get("TUZI_BLANK_MODEL") or BLANK_MODEL_DEFAULT


def _tuzi_chat(messages, model=None):
    """保留可 monkeypatch 的独立调用点，同时复用 geometry.llm 的 tu-zi 客户端。"""
    return geometry_llm._tuzi_chat(messages, model=model)


def _positive(value, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"LLM 毛坯缺少正数 {field}") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"LLM 毛坯缺少正数 {field}")
    return round(number, 4)


def _payload_envelope(payload: dict) -> dict:
    return {
        key: payload.get(key)
        for key in ("length", "width", "height", "diameter")
        if payload.get(key) not in (None, "")
    }


def _geometry_bbox(geometry: dict | None) -> dict:
    if not isinstance(geometry, dict):
        return {}
    box = geometry.get("bounding_box_mm") or geometry
    if not isinstance(box, dict):
        return {}
    return {
        axis: box.get(axis)
        for axis in ("x", "y", "z")
        if box.get(axis) not in (None, "")
    }


def geometry_payload(payload: dict, geometry: dict | None = None) -> dict:
    """把已知 bbox 补成 blank.decide 可消费的几何包络。"""
    normalized = dict(payload)
    bbox = _geometry_bbox(geometry)
    dimensions = []
    for axis in ("x", "y", "z"):
        try:
            value = float(bbox[axis])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            dimensions.append(value)
    dimensions.sort(reverse=True)
    if len(dimensions) == 3 and (
        normalized.get("length") in (None, "")
        or normalized.get("width") in (None, "")
        or normalized.get("height") in (None, "")
    ):
        normalized["length"], normalized["width"], normalized["height"] = dimensions
    return normalized


def _read_step(step_path: str | None, step_text: str | None) -> tuple[str, bool]:
    if step_text:
        text = (
            step_text.decode("ascii", errors="replace")
            if isinstance(step_text, bytes)
            else str(step_text)
        )
        limit = int(
            os.environ.get("TUZI_BLANK_MAX_STEP_CHARS")
            or MAX_STEP_CHARS_DEFAULT
        )
        return text[:limit], len(text) > limit
    if not step_path:
        return "", False
    limit = int(
        os.environ.get("TUZI_BLANK_MAX_STEP_CHARS")
        or MAX_STEP_CHARS_DEFAULT
    )
    return geometry_llm.read_step_ascii(step_path, max_chars=limit)


def build_messages(
    payload: dict,
    *,
    step_text: str = "",
    geometry: dict | None = None,
    truncated: bool = False,
) -> list[dict]:
    context = {
        "known_envelope_mm": _payload_envelope(payload),
        "geometry_bbox_mm": _geometry_bbox(geometry),
        "feature_types": [
            feature.get("type")
            for feature in payload.get("features") or []
            if isinstance(feature, dict) and feature.get("type")
        ],
        "step_truncated": truncated,
    }
    prompt = (
        f"上下文：{json.dumps(context, ensure_ascii=False)}\n"
        + (f"\nSTEP:\n{step_text}" if step_text else "\n未提供 STEP；按已知包络判断。")
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def map_suggestion(raw) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("LLM 毛坯返回须为 JSON 对象")
    candidate = raw.get("blank") if isinstance(raw.get("blank"), dict) else raw
    blank_type = candidate.get("blank_type")
    if blank_type not in _LABELS:
        raise ValueError("LLM blank_type 须为 plate/square_bar/round_bar")
    envelope = (
        candidate.get("envelope_mm")
        or candidate.get("projection_mm")
        or candidate.get("dimensions")
    )
    if not isinstance(envelope, dict):
        envelope = candidate
    if blank_type == "round_bar":
        mapped_envelope = {
            "length": _positive(envelope.get("length"), "length"),
            "diameter": _positive(
                envelope.get("diameter", envelope.get("diameter_mm")),
                "diameter",
            ),
        }
    else:
        mapped_envelope = {
            key: _positive(envelope.get(key), key)
            for key in ("length", "width", "height")
        }
    rationale = str(
        candidate.get("rationale")
        or candidate.get("reason")
        or candidate.get("llm_rationale")
        or ""
    ).strip()
    return {
        "blank_type": blank_type,
        "label": _LABELS[blank_type],
        "envelope_mm": mapped_envelope,
        "rationale": rationale[:300],
    }


def _decision_payload(payload: dict, suggestion: dict) -> dict:
    decision_payload = dict(payload)
    decision_payload.pop("stock_type", None)
    decision_payload["blank_type"] = suggestion["blank_type"]
    decision_payload.update(suggestion["envelope_mm"])
    if suggestion["blank_type"] == "round_bar":
        decision_payload["width"] = None
        decision_payload["height"] = None
    else:
        decision_payload["diameter"] = None
    return decision_payload


def _same_envelope(left: dict, right: dict) -> bool:
    if set(left) != set(right):
        return False
    return all(
        math.isclose(float(left[key]), float(right[key]), rel_tol=0, abs_tol=1e-6)
        for key in left
    )


def _stock_table_gaps(blank_type: str) -> list[str]:
    if blank_type == "round_bar":
        return ["标准库存长度表缺失：length 使用现有 5 mm 向上取整启发式"]
    if blank_type == "plate":
        return [
            "标准库存长宽表缺失：length/width 使用现有 5 mm 向上取整启发式"
        ]
    return [
        "方料标准库存尺寸表缺失：length/width/height 使用现有 5 mm 向上取整启发式"
    ]


def _observe(
    decision: dict,
    *,
    source: str,
    model: str | None,
    normalized: bool = False,
    rationale: str = "",
    error: Exception | None = None,
    cache_hit: bool = False,
) -> dict:
    observed = dict(decision)
    observed.update({
        "source": source,
        "model": model,
        "pending": False,
        "decide_normalized_envelope": bool(normalized),
        "gaps": _stock_table_gaps(decision["blank_type"]),
    })
    if source == "llm":
        observed["cache_hit"] = bool(cache_hit)
    if rationale:
        observed["llm_rationale"] = rationale
    if error is not None:
        observed["llm_error"] = str(error)[:300]
    return observed


def geometry_decide(payload: dict, *, geometry: dict | None = None) -> dict:
    """默认快路径：只执行确定性的 geometry 毛坯决策，不读取 STEP、不调用 LLM。"""
    payload = geometry_payload(payload, geometry)
    return _observe(
        blank.decide(payload),
        source="geometry",
        model=None,
    )


def _decision_from_suggestion(
    payload: dict,
    suggestion: dict,
    *,
    model: str,
    cache_hit: bool = False,
) -> dict:
    decision = blank.decide(_decision_payload(payload, suggestion))
    normalized = (
        decision["blank_type"] != suggestion["blank_type"]
        or decision["label"] != suggestion["label"]
        or not _same_envelope(
            decision["envelope_mm"],
            suggestion["envelope_mm"],
        )
    )
    return _observe(
        decision,
        source="llm",
        model=model,
        normalized=normalized,
        rationale=suggestion["rationale"],
        cache_hit=cache_hit,
    )


def _step_sha256(step_path: str | None, step_text: str | bytes | None) -> str:
    hasher = hashlib.sha256()
    if step_text is not None:
        hasher.update(
            step_text
            if isinstance(step_text, bytes)
            else str(step_text).encode("utf-8")
        )
        return hasher.hexdigest()
    if not step_path:
        hasher.update(b"<no-step>")
        return hasher.hexdigest()
    with open(step_path, "rb") as step_file:
        for chunk in iter(lambda: step_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def input_fingerprint(
    payload: dict,
    *,
    step_path: str | None = None,
    step_text: str | bytes | None = None,
) -> str:
    """缓存键只绑定 STEP 内容与 geometry 包络，不绑定报价公式或库存规格。"""
    envelope = {
        key: payload.get(key)
        for key in ("length", "width", "height", "diameter")
        if payload.get(key) not in (None, "")
    }
    fingerprint_input = json.dumps(
        {
            "version": 1,
            "step_sha256": _step_sha256(step_path, step_text),
            "envelope_mm": envelope,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(fingerprint_input).hexdigest()


def decide_cached(
    payload: dict,
    conn,
    *,
    step_path: str | None = None,
    step_text: str | None = None,
    geometry: dict | None = None,
) -> dict:
    """显式 LLM 路径：命中耐久缓存则跳过 tu-zi，失败仍返回 geometry。"""
    model = blank_model()
    payload = geometry_payload(payload, geometry)
    try:
        fingerprint = input_fingerprint(
            payload,
            step_path=step_path,
            step_text=step_text,
        )
        cached = conn.execute(
            "SELECT model,suggestion_json FROM blank_llm_cache WHERE fingerprint=?",
            (fingerprint,),
        ).fetchone()
        if cached:
            try:
                suggestion = map_suggestion(json.loads(cached["suggestion_json"]))
                return _decision_from_suggestion(
                    payload,
                    suggestion,
                    model=cached["model"],
                    cache_hit=True,
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                conn.execute(
                    "DELETE FROM blank_llm_cache WHERE fingerprint=?",
                    (fingerprint,),
                )
                conn.commit()

        text, truncated = _read_step(step_path, step_text)
        suggestion = map_suggestion(_tuzi_chat(
            build_messages(
                payload,
                step_text=text,
                geometry=geometry,
                truncated=truncated,
            ),
            model=model,
        ))
        conn.execute(
            "INSERT OR REPLACE INTO blank_llm_cache"
            "(fingerprint,model,suggestion_json,updated_at) "
            "VALUES (?,?,?,datetime('now'))",
            (
                fingerprint,
                model,
                json.dumps(suggestion, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
        return _decision_from_suggestion(
            payload,
            suggestion,
            model=model,
        )
    except Exception as exc:
        return _observe(
            blank.decide(payload),
            source="geometry",
            model=model,
            error=exc,
        )


def decide(
    payload: dict,
    *,
    step_path: str | None = None,
    step_text: str | None = None,
    geometry: dict | None = None,
) -> dict:
    """LLM 建议落入 #165 契约；任何 LLM 错误都回退现有几何决策。"""
    model = blank_model()
    payload = geometry_payload(payload, geometry)
    try:
        text, truncated = _read_step(step_path, step_text)
        raw = _tuzi_chat(
            build_messages(
                payload,
                step_text=text,
                geometry=geometry,
                truncated=truncated,
            ),
            model=model,
        )
        return _decision_from_suggestion(
            payload,
            map_suggestion(raw),
            model=model,
        )
    except Exception as exc:
        return _observe(
            blank.decide(payload),
            source="geometry",
            model=model,
            error=exc,
        )
