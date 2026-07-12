"""工程文件本地内容寻址存储。"""
import hashlib
import os
from pathlib import Path


STEP_EXTENSIONS = {"step", "stp"}
PDF_EXTENSIONS = {"pdf"}
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_JOB_BYTES = 150 * 1024 * 1024


def storage_root() -> Path:
    configured = os.environ.get("CNCFLOW_FILE_STORAGE")
    if configured:
        return Path(configured)
    # 生产systemd显式配置/var/lib；本地开发默认使用仓库数据目录，避免权限问题。
    return Path(__file__).resolve().parents[2] / "data" / "uploads"


def detect_type(filename: str, prefix: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in STEP_EXTENSIONS and b"ISO-10303-21" in prefix[:4096].upper():
        return "step"
    if ext in PDF_EXTENSIONS and prefix.startswith(b"%PDF-"):
        return "pdf"
    raise ValueError("文件扩展名与实际内容不匹配；MVP仅支持有效的 STP 和 PDF")


def store_upload(file_storage, job_id: str, role: str) -> dict:
    """流式写入临时文件、计算完整SHA-256，并原子移动到内容寻址路径。"""
    root = storage_root()
    incoming = root / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    temp = incoming / f"{job_id}-{role}.part"
    hasher = hashlib.sha256()
    size = 0
    prefix = bytearray()
    try:
        with temp.open("wb") as output:
            while True:
                chunk = file_storage.stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ValueError("单个文件不能超过100MB")
                if len(prefix) < 4096:
                    prefix.extend(chunk[:4096 - len(prefix)])
                hasher.update(chunk)
                output.write(chunk)
        detected = detect_type(file_storage.filename or "", bytes(prefix))
        digest = hasher.hexdigest()
        destination = root / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            temp.unlink()
        else:
            os.replace(temp, destination)
        return {
            "role": role, "original_name": file_storage.filename, "storage_path": str(destination),
            "sha256": digest, "size_bytes": size, "detected_type": detected,
        }
    except Exception:
        temp.unlink(missing_ok=True)
        raise
