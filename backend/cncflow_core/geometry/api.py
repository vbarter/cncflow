"""POST /api/v1/geometry/parse — multipart STEP in, feature JSON out."""
import os
import tempfile

from flask import Blueprint, jsonify, request

from ..ingestion.storage import MAX_FILE_BYTES, detect_type
from .plugins import plugin_summaries
from .service import contract, parse_step_file

bp = Blueprint("geometry", __name__)


def _error(message, status=400):
    body = {
        "error": message,
        "service": "geometry",
        "feature_schema": "hole-v3",
        "plugins": plugin_summaries(),
        "features": [],
    }
    if status == 400:
        body["contract"] = contract()
    return jsonify(body), status


@bp.get("/api/v1/geometry/contract")
def geometry_contract():
    return jsonify(contract())


@bp.post("/api/v1/geometry/parse")
def parse_geometry():
    upload = request.files.get("step_file") or request.files.get("file")
    if upload is None or not (upload.filename or "").strip():
        return _error("请上传 step_file（.step/.stp）")

    name = (upload.filename or "").lower()
    if not (name.endswith(".step") or name.endswith(".stp")):
        return _error("只接受 .step / .stp")

    suffix = ".stp" if name.endswith(".stp") else ".step"
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        os.close(fd)
        upload.save(path)
        size = os.path.getsize(path)
        if size == 0:
            return _error("STEP文件为空")
        if size > MAX_FILE_BYTES:
            return _error("单个文件不能超过100MB")
        with open(path, "rb") as handle:
            prefix = handle.read(4096)
        try:
            detected = detect_type(upload.filename or "part.step", prefix)
        except ValueError as exc:
            return _error(str(exc))
        if detected != "step":
            return _error("仅支持STEP文件")
        try:
            return jsonify(parse_step_file(path))
        except ValueError as exc:
            return _error(str(exc), 400)
        except RuntimeError as exc:
            # CadQuery/OCP may be absent in local pytest; still expose plugin registry.
            status = 503 if "CadQuery" in str(exc) else 400
            return _error(str(exc), status)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
