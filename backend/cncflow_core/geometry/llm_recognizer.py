"""通过 tu-zi OpenAI-compatible API 从 STEP 文本识别制造特征。"""
import base64
import json
import math
import os
import re
from pathlib import Path

from cncflow_core.ingestion.step_parser import SURFACE_FROM_POSITION, through_cut_depth


TUZI_BASE_URL = "https://api.tu-zi.com/v1"
DEFAULT_MODEL = "gpt-6-astra"

FEATURE_PROMPT = """你是 CNC STEP 制造特征解析器。读取附带的 STEP Part 21 ASCII 文件，
只返回可由文件几何支持的制造特征。返回 JSON 对象，顶层格式必须是：
{"features": [ ... ]}

仅允许以下六类 type 和字段（尺寸单位均为 mm）：
- hole: diameter_mm, depth_mm, hole_type, position_type, cut_depth_mm, location, axis
- thread: diameter_mm, pitch, thread_length, location, axis
- face: length, width, face_position, area, location, axis
- surface: surface_type, curvature_radius, position, location, axis
- step: profile_type, length, height, width, location, axis
- slot: pocket_type, length, width, depth, corner_radius, location, axis

规则：
1. 每个实际出现的特征单独输出，不要把多个同尺寸孔合并。
2. hole_type 使用 through/blind；position_type 使用 垂直/倾斜/曲面/侧向/深腔。
3. face_position 使用 水平/垂直/倾斜；pocket_type 使用 开放/半开放/封闭。
4. location 与 axis 均使用 {"x": number, "y": number, "z": number}。
5. 不确定的特征不要猜；可以省略。不要把外圆柱、倒角、圆角或槽角误报成孔/曲面。
6. “滑轴”是报价切削参数滑块矩阵，不是 CAD 几何特征，绝不能输出 slider/滑轴特征。
7. 不要输出 Markdown、解释、工序、刀具、成本或任何上述列表外的 feature type。
"""

TYPE_ALIASES = {
    "hole": "hole",
    "孔": "hole",
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
    "slot": "slot",
    "pocket": "slot",
    "槽": "slot",
    "槽腔": "slot",
}

CATEGORY_KEYS = {
    "holes": "hole",
    "孔": "hole",
    "threads": "thread",
    "螺纹": "thread",
    "faces": "face",
    "planes": "face",
    "平面": "face",
    "surfaces": "surface",
    "曲面": "surface",
    "steps": "step",
    "台阶轮廓": "step",
    "slots": "slot",
    "pockets": "slot",
    "槽腔": "slot",
}

SUBTYPES = {
    "hole": "recognized_hole",
    "thread": "recognized_thread",
    "face": "recognized_face",
    "surface": "recognized_surface",
    "step": "recognized_step",
    "slot": "recognized_slot",
}


def _json_object(content):
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("tu-zi 返回内容不是 JSON 对象")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("tu-zi 返回 JSON 不是对象")
    return value


def _source(item):
    dimensions = item.get("dimensions")
    return {**dimensions, **item} if isinstance(dimensions, dict) else item


def _number(source, key, *, positive=False, nonnegative=False):
    value = source.get(key)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        value = match.group(0) if match else None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if positive and value <= 0:
        return None
    if nonnegative and value < 0:
        return None
    return round(value, 6)


def _vector(value):
    if isinstance(value, str):
        value = {
            "+X": (1, 0, 0),
            "-X": (-1, 0, 0),
            "+Y": (0, 1, 0),
            "-Y": (0, -1, 0),
            "+Z": (0, 0, 1),
            "-Z": (0, 0, -1),
        }.get(value.strip().upper())
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        value = {"x": value[0], "y": value[1], "z": value[2]}
    if not isinstance(value, dict):
        return None
    result = {}
    for key in ("x", "y", "z"):
        number = _number(value, key)
        if number is None:
            return None
        result[key] = number
    return result


def _confidence(source):
    value = _number(source, "confidence")
    if value is None:
        return 0.8
    if value > 1:
        value /= 100
    return round(min(max(value, 0), 1), 3)


def _selected(source, default=True):
    value = source.get("selected")
    return value if isinstance(value, bool) else default


def _base_feature(kind, index, source, dimensions, *, selected=True):
    feature = {
        "feature_id": f"{kind}-{index}",
        "type": "pocket" if kind == "slot" else kind,
        "subtype": SUBTYPES[kind],
        "selected": _selected(source, selected),
        **dimensions,
        "dimensions": dict(dimensions),
        "location": _vector(source.get("location")),
        "axis": _vector(source.get("axis")),
        "occurrences": 1,
        "confidence": _confidence(source),
        "evidence": ["tu-zi STEP geometry"],
        "warnings": [],
    }
    return feature


def _map_hole(index, source):
    diameter = _number(source, "diameter_mm", positive=True)
    depth = _number(source, "depth_mm", positive=True)
    if diameter is None or depth is None:
        return None
    raw_type = str(source.get("hole_type") or "").strip().lower()
    hole_type = {
        "through": "through",
        "through_hole": "through",
        "通孔": "through",
        "贯穿": "through",
        "blind": "blind",
        "blind_hole": "blind",
        "盲孔": "blind",
    }.get(raw_type)
    position = str(source.get("position_type") or "").strip() or None
    complete = hole_type is not None and position is not None
    cut_depth = _number(source, "cut_depth_mm", positive=True)
    if cut_depth is None and hole_type is not None:
        cut_depth = through_cut_depth(diameter, depth, hole_type)
    dimensions = {
        "diameter_mm": diameter,
        "depth_mm": depth,
        "hole_type": hole_type,
        "position_type": position,
        "cut_depth_mm": cut_depth,
    }
    feature = _base_feature("hole", index, source, dimensions, selected=complete)
    feature.update({
        "h_over_d": round(depth / diameter, 4),
        "surface": SURFACE_FROM_POSITION.get(position),
        "bottom_shape": str(source.get("bottom_shape") or "cone"),
        "thread": None,
    })
    if not complete:
        feature["warnings"].append("孔的 hole_type/position_type 不完整，默认不进入报价")
    return feature


def _map_thread(index, source):
    dimensions = {
        "diameter_mm": _number(source, "diameter_mm", positive=True),
        "pitch": _number(source, "pitch", positive=True),
        "thread_length": _number(source, "thread_length", positive=True),
    }
    if any(value is None for value in dimensions.values()):
        return None
    return _base_feature("thread", index, source, dimensions)


def _map_face(index, source):
    length = _number(source, "length", positive=True)
    width = _number(source, "width", positive=True)
    if length is None or width is None:
        return None
    dimensions = {
        "length": length,
        "width": width,
        "face_position": str(source.get("face_position") or "").strip() or None,
    }
    area = _number(source, "area", positive=True)
    if area is not None:
        dimensions["area"] = area
    complete = dimensions["face_position"] is not None
    feature = _base_feature("face", index, source, dimensions, selected=complete)
    if not complete:
        feature["warnings"].append("平面的 face_position 不完整，默认不进入报价")
    return feature


def _map_surface(index, source):
    surface_type = str(source.get("surface_type") or "").strip()
    if not surface_type:
        return None
    dimensions = {
        "surface_type": surface_type,
        "curvature_radius": _number(source, "curvature_radius", positive=True),
        "position": str(source.get("position") or "").strip() or None,
    }
    return _base_feature("surface", index, source, dimensions)


def _map_step(index, source):
    dimensions = {
        "profile_type": str(source.get("profile_type") or "").strip() or None,
        "length": _number(source, "length", positive=True),
        "height": _number(source, "height", positive=True),
    }
    if any(value is None for value in dimensions.values()):
        return None
    feature = _base_feature("step", index, source, dimensions)
    width = _number(source, "width", positive=True)
    if width is not None:
        feature["width"] = width
    return feature


def _map_slot(index, source):
    dimensions = {
        "pocket_type": str(source.get("pocket_type") or "").strip() or None,
        "length": _number(source, "length", positive=True),
        "width": _number(source, "width", positive=True),
        "depth": _number(source, "depth", positive=True),
        "corner_radius": _number(source, "corner_radius", nonnegative=True),
    }
    if any(value is None for value in dimensions.values()):
        return None
    return _base_feature("slot", index, source, dimensions)


MAPPERS = {
    "hole": _map_hole,
    "thread": _map_thread,
    "face": _map_face,
    "surface": _map_surface,
    "step": _map_step,
    "slot": _map_slot,
}


def _raw_features(payload):
    features = payload.get("features")
    if isinstance(features, list):
        return features
    flattened = []
    for key, kind in CATEGORY_KEYS.items():
        values = payload.get(key)
        if isinstance(values, list):
            flattened.extend({**item, "type": kind} for item in values if isinstance(item, dict))
    return flattened


def map_tuzi_features(payload, warnings=None):
    """将模型 JSON 映射为 FeatureReview/报价引擎当前使用的 feature dict。"""
    warnings = warnings if warnings is not None else []
    counters = {kind: 0 for kind in MAPPERS}
    mapped = []
    for raw_index, item in enumerate(_raw_features(payload)):
        if not isinstance(item, dict):
            warnings.append(f"tu-zi feature[{raw_index}] 不是对象，已忽略")
            continue
        raw_type = str(item.get("type") or item.get("feature_type") or "").strip().lower()
        kind = TYPE_ALIASES.get(raw_type)
        if kind is None:
            warnings.append(f"tu-zi feature[{raw_index}] 类型 {raw_type or 'missing'} 不受支持，已忽略")
            continue
        source = _source(item)
        feature = MAPPERS[kind](counters[kind], source)
        if feature is None:
            warnings.append(f"tu-zi feature[{raw_index}] 的 {kind} 必填字段无效，已忽略")
            continue
        counters[kind] += 1
        mapped.append(feature)
    return mapped


def _safe_error(exc):
    message = str(exc)
    key = os.environ.get("TUZI_API_KEY")
    return message.replace(key, "[redacted]") if key else message


def _client():
    api_key = os.environ.get("TUZI_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 TUZI_API_KEY")
    from openai import OpenAI

    timeout = float(os.environ.get("TUZI_FEATURE_TIMEOUT_SECONDS") or os.environ.get("TUZI_TIMEOUT_SECONDS", "90"))
    return OpenAI(
        api_key=api_key,
        base_url=TUZI_BASE_URL,
        timeout=timeout,
        max_retries=0,
    )


def _request(client, model, content):
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return only one valid JSON object."},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
    )
    return _json_object(response.choices[0].message.content)


def recognize_step_features(path, image_urls=None, client=None):
    """优先发送 chat file part；tu-zi 拒绝时回退完整 STEP ASCII 文本。"""
    model = os.environ.get("TUZI_MODEL") or DEFAULT_MODEL
    client = client or _client()
    step_bytes = Path(path).read_bytes()
    encoded = base64.b64encode(step_bytes).decode("ascii")
    images = [
        {"type": "image_url", "image_url": {"url": url}}
        for url in (image_urls or [])
        if isinstance(url, str) and url.strip()
    ]
    file_content = [
        {"type": "text", "text": FEATURE_PROMPT},
        {
            "type": "file",
            "file": {
                "filename": Path(path).name,
                "file_data": f"data:text/plain;base64,{encoded}",
            },
        },
        *images,
    ]
    warnings = []
    try:
        raw = _request(client, model, file_content)
        input_mode = "file_part"
    except Exception as file_exc:
        warnings.append(f"tu-zi file part 失败，已回退 STEP ASCII: {_safe_error(file_exc)}")
        try:
            step_text = step_bytes.decode("utf-8", errors="replace")
            raw = _request(
                client,
                model,
                [
                    {"type": "text", "text": f"{FEATURE_PROMPT}\n\nSTEP ASCII:\n{step_text}"},
                    *images,
                ],
            )
            input_mode = "text_fallback"
        except Exception as text_exc:
            raise RuntimeError(
                "tu-zi STEP 特征识别失败；"
                f"file part: {_safe_error(file_exc)}；"
                f"ASCII fallback: {_safe_error(text_exc)}"
            ) from text_exc
    features = map_tuzi_features(raw, warnings)
    if not features:
        warnings.append("tu-zi 未返回可用的 CAD 制造特征")
    return {
        "provider": "tu-zi",
        "model": model,
        "input_mode": input_mode,
        "features": features,
        "warnings": warnings,
    }
