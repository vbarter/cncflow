"""几何特征服务 HTTP 契约。询价本轮不改打此接口。"""
import os
import tempfile

from flask import Blueprint, current_app, jsonify, request

from ..common.db import DEFAULT_DB_PATH
from .plugins import list_plugins
from .service import contract

bp = Blueprint("geometry", __name__)


_DROP_FROM_JSON = object()


def _public_json_value(value):
    """递归剔除内部字段和二进制值，避免 HTTP 响应泄漏/序列化失败。"""
    if isinstance(value, dict):
        public = {}
        for key, item in value.items():
            if str(key).startswith("_"):
                continue
            cleaned = _public_json_value(item)
            if cleaned is not _DROP_FROM_JSON:
                public[key] = cleaned
        return public
    if isinstance(value, (list, tuple)):
        public = []
        for item in value:
            cleaned = _public_json_value(item)
            if cleaned is not _DROP_FROM_JSON:
                public.append(cleaned)
        return public
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _DROP_FROM_JSON
    return value


@bp.get("/api/v1/geometry/contract")
def geometry_contract():
    return jsonify(contract())


@bp.post("/api/v1/geometry/parse")
def geometry_parse():
    step = request.files.get("step_file")
    if step is None or not step.filename:
        return jsonify({"error": "请上传 step_file（.step/.stp）", "contract": contract()}), 400
    name = step.filename.lower()
    if not (name.endswith(".step") or name.endswith(".stp")):
        return jsonify({"error": "只接受 .step / .stp"}), 400
    suffix = ".stp" if name.endswith(".stp") else ".step"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        step.save(path)
        from .service import parse_step_file
        force_reparse = (
            request.values.get("force_reparse", "").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        result = parse_step_file(
            path,
            include_mesh=False,
            force_reparse=force_reparse,
            cache_db_path=(
                current_app.config.get("DB_PATH")
                or str(DEFAULT_DB_PATH)
            ),
        )
        return jsonify(_public_json_value(result))
    except RuntimeError as exc:
        return jsonify({
            "error": str(exc),
            "service": "geometry",
            "plugins": list_plugins(),
            "features": [],
        }), 503
    except Exception as exc:
        return jsonify({"error": str(exc), "plugins": list_plugins()}), 400
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
