"""tu-zi gpt-6-astra 特征抽取：STEP 文本 → 下游 feature 模型。

主路径。几何插件只在 CNCFLOW_FEATURE_PARSER=geometry / dual 回退。
不走 /v1/files，不把 STEP 当 chat file part。
"""
from __future__ import annotations

import json
import os
import re

from cncflow_core.ingestion.step_parser import (
    SURFACE_FROM_POSITION,
    through_cut_depth,
)

TUZI_HOST = "https://api.tu-zi.com"
FEATURE_MODEL_DEFAULT = "gpt-6-astra"
PARSER_LLM = "llm"
PARSER_GEOMETRY = "geometry"
PARSER_DUAL = "dual"
MAX_STEP_CHARS_DEFAULT = 800_000

_TYPE_ALIASES = {
    "hole": "hole",
    "孔": "hole",
    "通孔": "hole",
    "盲孔": "hole",
    "outer_cylinder": "outer_cylinder",
    "outer-cylinder": "outer_cylinder",
    "od": "outer_cylinder",
    "shaft": "outer_cylinder",
    "滑轴": "outer_cylinder",
    "外圆": "outer_cylinder",
    "外圆柱": "outer_cylinder",
    "轴": "outer_cylinder",
    "thread": "thread",
    "螺纹": "thread",
    "face": "face",
    "plane": "face",
    "平面": "face",
    "surface": "surface",
    "曲面": "surface",
    "step": "step",
    "台阶": "step",
    "台阶轮廓": "step",
    "pocket": "pocket",
    "slot": "slot",
    "槽": "slot",
    "腔": "pocket",
    "槽腔": "pocket",
    "型腔": "pocket",
    "groove": "slot",
    "channel": "slot",
    "open_slot": "slot",
    "openslot": "slot",
    "rectangular_slot": "slot",
    "rect_slot": "slot",
    "rect_open_slot": "slot",
    "milled_slot": "slot",
    "u_slot": "slot",
    "prismatic_slot": "slot",
    "prismatic_pocket": "pocket",
    "cavity": "pocket",
    "recess": "pocket",
    "keyway": "slot",
    "t_slot": "slot",
    "tslot": "slot",
    "pocket_or_slot": "pocket",
    "slot_or_pocket": "slot",
    "pocket_or_step": "pocket",
    "step_or_pocket": "pocket",
    "开口槽": "slot",
    "开放槽": "slot",
    "通槽": "slot",
    "铣槽": "slot",
    "矩形槽": "slot",
    "开槽": "slot",
    "槽口": "slot",
    "u形槽": "slot",
    "u型槽": "slot",
    "键槽": "slot",
    "t型槽": "slot",
    "t型": "slot",
    "开口型腔": "pocket",
    "封闭槽": "slot",
}

_HOLE_TYPE = {
    "through": "through",
    "blind": "blind",
    "通孔": "through",
    "盲孔": "blind",
    "通": "through",
    "盲": "blind",
}
_POSITION = {
    "垂直": "垂直",
    "倾斜": "倾斜",
    "曲面": "曲面",
    "侧向": "侧向",
    "深腔": "深腔",
    "vertical": "垂直",
    "top": "垂直",
    "inclined": "倾斜",
    "curved": "曲面",
    "side": "侧向",
    "deep": "深腔",
}
_BOTTOM = {
    "cone": "cone",
    "flat": "flat",
    "锥底": "cone",
    "conical": "cone",
    "平底": "flat",
}
_FACE_POS = {"水平": "水平", "垂直": "垂直", "倾斜": "倾斜", "horizontal": "水平", "vertical": "垂直", "inclined": "倾斜"}
_POCKET = {
    "开放": "开放", "封闭": "封闭", "键槽": "键槽", "T型": "T型", "T型槽": "T型槽",
    "open": "开放", "closed": "封闭", "keyway": "键槽", "t-slot": "T型",
    "opened": "开放", "open_slot": "开放", "through_slot": "开放",
    "side_open": "开放", "开口": "开放", "开口槽": "开放", "通槽": "开放",
    "enclosed": "封闭", "closed_pocket": "封闭",
    "t型槽": "T型槽", "t型": "T型",
}
_ID_PREFIX = {
    "hole": "hole",
    "outer_cylinder": "od",
    "thread": "thread",
    "face": "face",
    "surface": "surface",
    "step": "step",
    "pocket": "slot",
    "slot": "slot",
}
_SUBTYPE = {
    "hole": "recognized_hole",
    "outer_cylinder": "boss_or_od",
    "thread": "recognized_thread",
    "face": "recognized_face",
    "surface": "recognized_surface",
    "step": "recognized_step",
    "pocket": "recognized_slot",
    "slot": "recognized_slot",
}

SYSTEM_PROMPT = """你是 CNC 制造特征识别器。根据 ISO-10303-21 STEP 文本（以及可选截图）抽出加工特征。
只返回一个 JSON 对象：{"features":[...]}。不要编造不存在的特征，不要报价。

类型与字段（与 cncflow 下游模型对齐，手册 ①）：

1) hole 孔 — 内圆柱空腔，不是外圆。
   必填: type, diameter_mm, depth_mm, hole_type(through|blind), position_type(垂直|倾斜|曲面|侧向|深腔)
   选填: bottom_shape(cone|flat), location{x,y,z}, axis{x,y,z}
   通孔 cut_depth = depth + 0.3D，由下游算，不必给。
   槽腔内角圆柱（D≈2R）不要当孔。螺纹底孔不要单独再出 hole。

2) outer_cylinder 滑轴/外圆/OD — 实体外圆柱。
   必填: type, diameter_mm, depth_mm
   selected 必须 false。不进孔工序链。

3) thread 螺纹 — 有牙型/螺旋才出。公称直径不是底孔。
   必填: type, diameter_mm, thread_length
   选填: pitch（缺省按粗牙：M8→1.25）

4) face 平面 — 外轮廓平面。
   必填: type, length, width
   选填: area, face_position(水平|垂直|倾斜)
   整板顶面才默认 selected=true；台阶肩顶不要勾选。

5) surface 曲面 — 自由曲面/凸凹面，不是孔壁，也不是槽底。
   必填: type, surface_type
   选填: curvature_radius, position(顶面|底面|侧面)

6) step 台阶轮廓 — 肩台，不是槽底。开口槽不要报成台阶。
   必填: type, length, height
   选填: width, profile_type(台阶|外轮廓|侧壁)

7) pocket / slot 槽腔 — 内凹型腔，含开口矩形槽。漏报比多报更糟。
   必填: type(pocket|slot), length, width, depth
   选填: corner_radius(R), pocket_type(开放|封闭|键槽|T型)
   开口矩形槽（一边通到毛坯侧面的 U/C 形凹槽）必须出 slot，pocket_type=开放。
   L=槽长（开口方向），W=槽宽，H/depth=槽深，R=封闭端/底角圆角。
   例：80×60×12 板、开口 40×10×8 R3 → slot L=40 W=10 depth=8 corner_radius=3 pocket_type=开放。
   槽底即使是平面也算出槽，不要改成 face 或 surface。
   槽角圆弧/部分圆柱（D≈2R）不是 hole，也不是 outer_cylinder。
   严禁只报 face、face+自由曲面、face+outer_cylinder 而漏掉槽腔。

坐标单位 mm，与 STEP CARTESIAN_POINT 一致。每个特征给 location 和 axis（法向或孔轴）。
feature_id 可省略，下游按类型编号。
"""


def feature_parser_mode():
    raw = (os.environ.get("CNCFLOW_FEATURE_PARSER") or "llm").strip().lower()
    if raw in {PARSER_LLM, PARSER_GEOMETRY, PARSER_DUAL}:
        return raw
    return PARSER_LLM


def tuzi_api_key():
    return os.environ.get("TUZI_API_KEY") or os.environ.get("VISION_API_KEY") or ""


def feature_model():
    """特征识别默认 gpt-6-astra，不跟 chat/PDF 的 TUZI_MODEL 绑死。"""
    return os.environ.get("TUZI_FEATURE_MODEL") or FEATURE_MODEL_DEFAULT


def llm_fallback_enabled():
    if feature_parser_mode() == PARSER_DUAL:
        return True
    return (os.environ.get("CNCFLOW_FEATURE_LLM_FALLBACK") or "").strip() in {"1", "true", "yes"}


def _json_object(content):
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("tu-zi 特征识别返回内容不是 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("tu-zi 特征识别返回 JSON 不是对象")
    return value


def _num(*values):
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, str):
            match = re.search(r"-?\d+(?:\.\d+)?", value)
            if not match:
                continue
            value = match.group(0)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:  # not NaN
            return number
    return None


def _xyz(value):
    if not isinstance(value, dict):
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            nums = [_num(value[0]), _num(value[1]), _num(value[2])]
            if all(n is not None for n in nums):
                return {"x": round(nums[0], 4), "y": round(nums[1], 4), "z": round(nums[2], 4)}
        return None
    nums = [_num(value.get("x"), value.get("X")), _num(value.get("y"), value.get("Y")), _num(value.get("z"), value.get("Z"))]
    if any(n is None for n in nums):
        return None
    return {"x": round(nums[0], 4), "y": round(nums[1], 4), "z": round(nums[2], 4)}


def _norm_type(raw):
    if raw is None:
        return None
    text = str(raw).strip()
    key = text.lower().replace(" ", "_").replace("-", "_")
    if key in _TYPE_ALIASES:
        return _TYPE_ALIASES[key]
    return _TYPE_ALIASES.get(text)


def read_step_ascii(path, max_chars=None):
    limit = max_chars
    if limit is None:
        limit = int(os.environ.get("TUZI_FEATURE_MAX_STEP_CHARS") or MAX_STEP_CHARS_DEFAULT)
    raw = open(path, "rb").read()
    text = raw.decode("ascii", errors="replace")
    if "ISO-10303-21" not in text[:200] and "ISO-10303-21" not in text[:800]:
        raise ValueError("文件不是 ASCII STEP（ISO-10303-21）")
    truncated = False
    if len(text) > limit:
        text = text[:limit]
        truncated = True
    return text, truncated


def _geometry_hint(geometry):
    if not isinstance(geometry, dict):
        return ""
    box = geometry.get("bounding_box_mm") or {}
    return (
        "\n已解析几何（仅供对照，特征以 STEP 为准）："
        f" bbox_mm={box.get('x')}×{box.get('y')}×{box.get('z')}"
        f" volume_cm3={geometry.get('volume_cm3')}"
        f" faces={geometry.get('face_count')}"
        f" types={geometry.get('surface_types')}\n"
    )


def _step_cavity_hint(step_text):
    if not step_text:
        return ""
    cyl = step_text.count("CYLINDRICAL_SURFACE")
    circ = len(re.findall(r"\bCIRCLE\s*\(", step_text))
    if cyl >= 2 or circ >= 2:
        return (
            "STEP 含多个圆柱/圆，先检查开口矩形槽的槽角 R（部分圆柱），"
            "不要报成 outer_cylinder 或 hole；有槽必须输出 slot/pocket。\n"
        )
    return ""


def build_messages(step_text, geometry=None, images=None):
    prompt = (
        SYSTEM_PROMPT
        + _geometry_hint(geometry)
        + _step_cavity_hint(step_text)
        + "\nSTEP:\n"
        + step_text
    )
    content = [{"type": "text", "text": prompt}]
    for image in images or []:
        if image:
            content.append({"type": "image_url", "image_url": {"url": image}})
    return [
        {"role": "system", "content": "只输出 JSON 对象 {\"features\":[...]}。"},
        {"role": "user", "content": content},
    ]


def _feature_attempts():
    try:
        return max(1, int(os.environ.get("TUZI_FEATURE_ATTEMPTS") or "2"))
    except (TypeError, ValueError):
        return 2


def _retryable_llm_error(exc):
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return True
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg or "temporar" in msg:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return status in {429, 502, 503, 504}


def _tuzi_complete(messages, model=None):
    api_key = tuzi_api_key()
    if not api_key:
        raise RuntimeError("未配置 TUZI_API_KEY，无法进行 LLM 特征识别")
    from openai import OpenAI

    timeout = float(os.environ.get("TUZI_FEATURE_TIMEOUT_SECONDS") or os.environ.get("TUZI_TIMEOUT_SECONDS") or "90")
    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("TUZI_BASE_URL") or f"{TUZI_HOST}/v1",
        timeout=timeout,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=model or feature_model(),
        messages=messages,
        response_format={"type": "json_object"},
    )
    choice = response.choices[0].message
    if getattr(choice, "refusal", None):
        raise RuntimeError(f"tu-zi 拒绝特征识别: {choice.refusal}")
    return _json_object(choice.content)


def _tuzi_chat(messages, model=None):
    """一次完成；超时/连接类错误默认再打一枪（台阶偶发超时）。"""
    last = None
    attempts = _feature_attempts()
    for index in range(attempts):
        try:
            return _tuzi_complete(messages, model)
        except Exception as exc:
            last = exc
            if not _retryable_llm_error(exc) or index + 1 >= attempts:
                raise
    raise last


def _dim(source, *keys):
    dim = source.get("dimensions") if isinstance(source.get("dimensions"), dict) else {}
    values = []
    for key in keys:
        values.append(source.get(key))
        values.append(dim.get(key))
    return _num(*values)


def _map_hole(raw, index):
    diameter = _dim(raw, "diameter_mm", "diameter", "D")
    depth = _dim(raw, "depth_mm", "depth", "H")
    if not diameter or diameter <= 0 or not depth or depth <= 0:
        raise ValueError("hole 缺少正数 diameter_mm / depth_mm")
    hole_type = _HOLE_TYPE.get(str(raw.get("hole_type") or raw.get("type_cn") or "through"), "through")
    if raw.get("type") in {"通孔", "盲孔"}:
        hole_type = _HOLE_TYPE[raw["type"]]
    position = _POSITION.get(str(raw.get("position_type") or raw.get("surface") or "垂直"), "垂直")
    bottom = _BOTTOM.get(str(raw.get("bottom_shape") or "cone"), "cone")
    cut = _dim(raw, "cut_depth_mm")
    if cut is None:
        cut = through_cut_depth(diameter, depth, hole_type)
    loc = _xyz(raw.get("location") or raw.get("center") or (raw.get("pose") or {}).get("origin"))
    axis = _xyz(raw.get("axis") or (raw.get("pose") or {}).get("axis")) or {"x": 0, "y": 0, "z": 1}
    feat = {
        "feature_id": raw.get("feature_id") or f"hole-{index}",
        "type": "hole",
        "subtype": "recognized_hole",
        "diameter_mm": round(diameter, 4),
        "depth_mm": round(depth, 4),
        "cut_depth_mm": round(cut, 4),
        "h_over_d": round(depth / diameter, 4),
        "hole_type": hole_type,
        "position_type": position,
        "surface": SURFACE_FROM_POSITION.get(position, "top"),
        "bottom_shape": bottom,
        "thread": raw.get("thread") if isinstance(raw.get("thread"), dict) else None,
        "dimensions": {"diameter_mm": round(diameter, 4), "depth_mm": round(depth, 4)},
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "axis": axis,
        "occurrences": int(raw.get("occurrences") or 1),
        "confidence": float(raw.get("confidence") or 0.8),
        "selected": raw.get("selected") is not False,
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", f"D={diameter:g}", f"H={depth:g}", hole_type, position]),
        "warnings": list(raw.get("warnings") or []),
        "source": "llm",
    }
    if loc:
        feat["pose"] = {
            "origin": loc,
            "axis": axis,
            "length_mm": round(depth, 4),
            "diameter_mm": round(diameter, 4),
        }
    return feat


def _map_od(raw, index):
    diameter = _dim(raw, "diameter_mm", "diameter", "D")
    depth = _dim(raw, "depth_mm", "depth", "length", "H")
    if not diameter or diameter <= 0 or not depth or depth <= 0:
        raise ValueError("outer_cylinder 缺少正数 diameter_mm / depth_mm")
    loc = _xyz(raw.get("location") or (raw.get("pose") or {}).get("origin"))
    axis = _xyz(raw.get("axis") or (raw.get("pose") or {}).get("axis")) or {"x": 0, "y": 0, "z": 1}
    return {
        "feature_id": raw.get("feature_id") or f"od-{index}",
        "type": "outer_cylinder",
        "subtype": "boss_or_od",
        "diameter_mm": round(diameter, 4),
        "depth_mm": round(depth, 4),
        "dimensions": {"diameter_mm": round(diameter, 4), "depth_mm": round(depth, 4)},
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "axis": axis,
        "occurrences": 1,
        "confidence": float(raw.get("confidence") or 0.78),
        "selected": False,
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", "outer cylinder"]),
        "warnings": ["外圆/滑轴，不进孔工序链"],
        "source": "llm",
    }


def _map_thread(raw, index):
    diameter = _dim(raw, "diameter_mm", "nominal_d", "D")
    length = _dim(raw, "thread_length", "depth_mm", "length", "H")
    if not diameter or diameter <= 0 or not length or length <= 0:
        raise ValueError("thread 缺少正数 diameter_mm / thread_length")
    pitch = _dim(raw, "pitch")
    if pitch is None:
        from cncflow_core.geometry.thread import infer_pitch
        pitch = infer_pitch(diameter) or 1.25
    loc = _xyz(raw.get("location") or (raw.get("pose") or {}).get("origin"))
    axis = _xyz(raw.get("axis") or (raw.get("pose") or {}).get("axis")) or {"x": 0, "y": 0, "z": 1}
    return {
        "feature_id": raw.get("feature_id") or f"thread-{index}",
        "type": "thread",
        "subtype": "recognized_thread",
        "selected": raw.get("selected") is not False,
        "diameter_mm": round(diameter, 4),
        "nominal_d": round(diameter, 4),
        "pitch": float(pitch),
        "thread_length": round(length, 4),
        "dimensions": {
            "diameter_mm": round(diameter, 4),
            "pitch": float(pitch),
            "thread_length": round(length, 4),
        },
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "axis": axis,
        "occurrences": 1,
        "confidence": float(raw.get("confidence") or 0.76),
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", f"D={diameter:g}", f"P={pitch:g}"]),
        "warnings": [],
        "source": "llm",
    }


def _map_face(raw, index):
    length = _dim(raw, "length", "L")
    width = _dim(raw, "width", "W")
    if not length or length <= 0 or not width or width <= 0:
        raise ValueError("face 缺少正数 length / width")
    area = _dim(raw, "area") or (length * width)
    pos = _FACE_POS.get(str(raw.get("face_position") or "水平"), "水平")
    loc = _xyz(raw.get("location") or (raw.get("pose") or {}).get("origin"))
    axis = _xyz(raw.get("axis") or (raw.get("pose") or {}).get("axis")) or {"x": 0, "y": 0, "z": 1}
    return {
        "feature_id": raw.get("feature_id") or f"face-{index}",
        "type": "face",
        "subtype": "recognized_face",
        "selected": bool(raw.get("selected")),
        "length": round(length, 4),
        "width": round(width, 4),
        "area": round(area, 4),
        "face_position": pos,
        "dimensions": {
            "length": round(length, 4),
            "width": round(width, 4),
            "area": round(area, 4),
            "face_position": pos,
        },
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "axis": axis,
        "occurrences": 1,
        "confidence": float(raw.get("confidence") or 0.74),
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", pos]),
        "warnings": [],
        "source": "llm",
    }


def _map_slot(raw, index, feat_type):
    length = _dim(raw, "length", "L", "slot_length", "l_mm", "length_mm")
    width = _dim(raw, "width", "W", "slot_width", "w_mm", "width_mm")
    depth = _dim(raw, "depth", "depth_mm", "height", "H", "slot_depth", "h_mm")
    if not length or length <= 0 or not width or width <= 0 or not depth or depth <= 0:
        raise ValueError("pocket/slot 缺少正数 length / width / depth")
    corner = _dim(raw, "corner_radius", "radius", "R", "fillet", "fillet_radius", "corner_r", "fillet_r", "radius_mm")
    if corner is None:
        corner = 1.0
    dim = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else {}
    raw_ptype = raw.get("pocket_type") or dim.get("pocket_type")
    if not raw_ptype and (raw.get("open") is True or raw.get("is_open") is True or dim.get("open") is True):
        raw_ptype = "开放"
    candidate = str(raw_ptype or ("开放" if feat_type == "slot" else "封闭"))
    ptype = _POCKET.get(candidate.lower(), _POCKET.get(candidate, "封闭"))
    loc = _xyz(raw.get("location") or (raw.get("pose") or {}).get("origin"))
    axis = _xyz(raw.get("axis") or (raw.get("pose") or {}).get("axis")) or {"x": 0, "y": 0, "z": 1}
    out_type = "slot" if feat_type == "slot" or ptype == "开放" else "pocket"
    return {
        "feature_id": raw.get("feature_id") or f"slot-{index}",
        "type": out_type,
        "subtype": "recognized_slot",
        "selected": raw.get("selected") is not False,
        "pocket_type": ptype,
        "length": round(length, 4),
        "width": round(width, 4),
        "depth": round(depth, 4),
        "corner_radius": round(corner, 4),
        "dimensions": {
            "length": round(length, 4),
            "width": round(width, 4),
            "depth": round(depth, 4),
            "corner_radius": round(corner, 4),
        },
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "axis": axis,
        "occurrences": 1,
        "confidence": float(raw.get("confidence") or 0.76),
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", ptype]),
        "warnings": [],
        "source": "llm",
    }


def _map_step(raw, index):
    length = _dim(raw, "length", "L")
    height = _dim(raw, "height", "depth", "depth_mm", "H")
    if not length or length <= 0 or not height or height <= 0:
        raise ValueError("step 缺少正数 length / height")
    width = _dim(raw, "width", "W")
    profile = raw.get("profile_type") or "台阶"
    loc = _xyz(raw.get("location") or (raw.get("pose") or {}).get("origin"))
    axis = _xyz(raw.get("axis") or (raw.get("pose") or {}).get("axis")) or {"x": 0, "y": 0, "z": 1}
    feat = {
        "feature_id": raw.get("feature_id") or f"step-{index}",
        "type": "step",
        "subtype": "recognized_step",
        "selected": raw.get("selected") is not False,
        "profile_type": profile,
        "length": round(length, 4),
        "height": round(height, 4),
        "dimensions": {"profile_type": profile, "length": round(length, 4), "height": round(height, 4)},
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "axis": axis,
        "occurrences": 1,
        "confidence": float(raw.get("confidence") or 0.74),
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", f"type={profile}"]),
        "warnings": [],
        "source": "llm",
    }
    if width and width > 0:
        feat["width"] = round(width, 4)
        feat["dimensions"]["width"] = round(width, 4)
    return feat


def _map_surface(raw, index):
    surface_type = raw.get("surface_type") or raw.get("kind") or "自由曲面"
    radius = _dim(raw, "curvature_radius", "radius", "R")
    loc = _xyz(raw.get("location") or (raw.get("pose") or {}).get("origin"))
    return {
        "feature_id": raw.get("feature_id") or f"surface-{index}",
        "type": "surface",
        "subtype": "recognized_surface",
        "selected": raw.get("selected") is not False,
        "surface_type": surface_type,
        "curvature_radius": None if radius is None else round(radius, 4),
        "position": raw.get("position") or "顶面",
        "dimensions": {
            "surface_type": surface_type,
            "curvature_radius": None if radius is None else round(radius, 4),
            "position": raw.get("position") or "顶面",
        },
        "location": loc or {"x": 0, "y": 0, "z": 0},
        "occurrences": 1,
        "confidence": float(raw.get("confidence") or 0.7),
        "evidence": list(raw.get("evidence") or ["llm-gpt-6-astra", f"surface_type={surface_type}"]),
        "warnings": [],
        "source": "llm",
    }


_MAPPERS = {
    "hole": _map_hole,
    "outer_cylinder": _map_od,
    "thread": _map_thread,
    "face": _map_face,
    "pocket": lambda raw, i: _map_slot(raw, i, "pocket"),
    "slot": lambda raw, i: _map_slot(raw, i, "slot"),
    "step": _map_step,
    "surface": _map_surface,
}

_NESTED_SLOT_KEYS = ("slots", "pockets", "cavities", "槽", "槽腔", "型腔")
_SLOT_SIGNAL = (
    "槽", "slot", "pocket", "groove", "channel", "型腔", "recess", "cavity",
    "keyway", "键槽", "开槽", "通槽",
)
_KEEP_TYPE = {"hole", "outer_cylinder", "thread"}


def _flatten_feature_items(raw_list):
    items = []
    for item in raw_list:
        if not isinstance(item, dict):
            items.append(item)
            continue
        items.append(item)
        for key in _NESTED_SLOT_KEYS:
            nested = item.get(key)
            if isinstance(nested, dict):
                children = [nested]
            elif isinstance(nested, list):
                children = nested
            else:
                continue
            for child in children:
                if not isinstance(child, dict):
                    continue
                extra = dict(child)
                default = "slot" if "slot" in key or key == "槽" else "pocket"
                extra.setdefault("type", extra.get("feature_type") or extra.get("kind") or default)
                items.append(extra)
    return items


def _slot_signal(item):
    text = " ".join(
        str(item.get(key) or "")
        for key in (
            "type", "feature_type", "kind", "name", "label", "description",
            "surface_type", "pocket_type", "subtype", "profile_type",
        )
    ).lower()
    return any(token in text for token in _SLOT_SIGNAL)


def _has_slot_lwh(item):
    length = _dim(item, "length", "L", "slot_length", "l_mm", "length_mm")
    width = _dim(item, "width", "W", "slot_width", "w_mm", "width_mm")
    depth = _dim(item, "depth", "depth_mm", "height", "H", "slot_depth", "h_mm")
    return bool(length and length > 0 and width and width > 0 and depth and depth > 0)


def _openish_pocket(item):
    dim = item.get("dimensions") if isinstance(item.get("dimensions"), dict) else {}
    raw = item.get("pocket_type") or dim.get("pocket_type")
    if raw is None and (item.get("open") is True or item.get("is_open") is True):
        return True
    mapped = _POCKET.get(str(raw).lower()) if raw is not None else None
    if mapped is None and raw is not None:
        mapped = _POCKET.get(str(raw))
    return mapped in {"开放", "键槽", "T型", "T型槽"}


def _maybe_slot_type(item, feat_type):
    """把漏报成 surface/face/未知名的开口槽拉回 slot/pocket。台阶/孔/外圆不抢。"""
    if feat_type in {"slot", "pocket"} or feat_type in _KEEP_TYPE:
        return feat_type
    signal = _slot_signal(item)
    openish = _openish_pocket(item)
    corner = _dim(item, "corner_radius", "radius", "R", "fillet", "fillet_radius")
    if feat_type == "step" and not (signal or openish):
        return feat_type
    if feat_type == "face" and not (signal or openish or corner):
        return feat_type
    if not _has_slot_lwh(item):
        return feat_type
    if not (signal or openish or corner or feat_type in {None, "surface"}):
        return feat_type
    raw = str(item.get("type") or item.get("feature_type") or item.get("kind") or "").lower()
    if feat_type == "pocket" or "pocket" in raw or "腔" in raw:
        return "pocket"
    return "slot"


def map_llm_features(payload):
    """把 tu-zi JSON 映射成 FeatureReview / quote 吃的 feature 列表。非法项记入 errors。"""
    if isinstance(payload, list):
        payload = {"features": payload}
    if not isinstance(payload, dict):
        raise ValueError("LLM 特征 JSON 须为对象")
    raw_list = payload.get("features")
    if raw_list is None:
        raise ValueError("LLM 特征 JSON 缺少 features 数组")
    if not isinstance(raw_list, list):
        raise ValueError("LLM features 须为数组")

    features = []
    errors = []
    counters = {key: 0 for key in _MAPPERS}
    for item in _flatten_feature_items(raw_list):
        if not isinstance(item, dict):
            errors.append("features 中有非对象项")
            continue
        feat_type = _norm_type(item.get("type") or item.get("feature_type") or item.get("kind"))
        feat_type = _maybe_slot_type(item, feat_type)
        if feat_type not in _MAPPERS:
            errors.append(f"未知特征类型: {item.get('type')!r}")
            continue
        try:
            mapped = _MAPPERS[feat_type](item, counters[feat_type])
        except ValueError as exc:
            errors.append(f"{feat_type}: {exc}")
            continue
        if not item.get("feature_id"):
            mapped["feature_id"] = f"{_ID_PREFIX[feat_type]}-{counters[feat_type]}"
        counters[feat_type] += 1
        features.append(mapped)

    if not features:
        detail = "；".join(errors) if errors else "features 为空"
        raise ValueError(f"LLM 未产出可用特征: {detail}")
    return {"features": features, "errors": errors}


def _has_cavity(features):
    return any(
        feat.get("type") in {"slot", "pocket"} or feat.get("subtype") == "recognized_slot"
        for feat in features or []
    )


def _thin_non_cavity(features):
    types = {feat.get("type") for feat in features or []}
    return bool(types) and types <= {"face", "surface", "outer_cylinder"}


def _slot_retry_enabled():
    return (os.environ.get("TUZI_FEATURE_SLOT_RETRY") or "1").strip().lower() not in {"0", "false", "no"}


SLOT_RETRY_PROMPT = """上次输出没有 slot/pocket。请复查 STEP。
若存在开口矩形槽/U 形凹槽（一边通到侧面），必须输出 type=slot 或 pocket，
pocket_type=开放，并给出 length/width/depth/corner_radius。
槽底不要报 surface，槽角圆弧不要报 hole 或 outer_cylinder。
仍输出全部特征（含外轮廓 face），只返回 JSON {\"features\":[...]}。不要报价。
"""


def _slot_retry_messages(step_text, geometry, previous):
    prev = json.dumps(previous, ensure_ascii=False)[:4000]
    prompt = (
        SLOT_RETRY_PROMPT
        + _geometry_hint(geometry)
        + _step_cavity_hint(step_text)
        + "\n上次输出:\n"
        + prev
        + "\n\nSTEP:\n"
        + step_text
    )
    return [
        {"role": "system", "content": "只输出 JSON 对象 {\"features\":[...]}。开口槽必须出 slot/pocket。"},
        {"role": "user", "content": [{"type": "text", "text": prompt}]},
    ]


def extract_step_features(path, geometry=None, images=None):
    """读 STEP 文本 → tu-zi gpt-6-astra → 映射后的 features。失败抛错。"""
    step_text, truncated = read_step_ascii(path)
    warnings = []
    if truncated:
        warnings.append(f"STEP 超过 {os.environ.get('TUZI_FEATURE_MAX_STEP_CHARS') or MAX_STEP_CHARS_DEFAULT} 字符，已截断后送模型")
    raw = _tuzi_chat(build_messages(step_text, geometry=geometry, images=images))
    mapped = map_llm_features(raw)
    if _slot_retry_enabled() and _thin_non_cavity(mapped["features"]) and not _has_cavity(mapped["features"]):
        try:
            retry_raw = _tuzi_chat(_slot_retry_messages(step_text, geometry, raw))
            retry_mapped = map_llm_features(retry_raw)
        except Exception as exc:
            warnings.append(f"LLM 开口槽补询失败（保留首次结果）: {exc}")
        else:
            if _has_cavity(retry_mapped["features"]):
                raw = retry_raw
                mapped = retry_mapped
                warnings.append("LLM 首次未出槽腔（仅面/曲面/外圆），补询已补 slot/pocket")
            else:
                warnings.append("LLM 补询仍未出槽腔")
                warnings.extend(f"LLM 跳过: {err}" for err in retry_mapped["errors"])
    warnings.extend(f"LLM 跳过: {err}" for err in mapped["errors"])
    return {
        "raw": raw,
        "features": mapped["features"],
        "warnings": warnings,
        "model": feature_model(),
        "truncated": truncated,
    }
