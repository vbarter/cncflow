"""几何特征服务 HTTP 契约。询价本轮不改打此接口。"""
import os
import tempfile

from flask import Blueprint, jsonify, request

from .plugins import list_plugins
from .service import contract

bp = Blueprint("geometry", __name__)


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
        return jsonify(parse_step_file(path))
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
