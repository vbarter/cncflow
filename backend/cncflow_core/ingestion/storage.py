"""工程文件存储：本地内容寻址，可选镜像到 Cloudflare R2。"""
import hashlib
import os
from pathlib import Path

from . import r2

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


def _object_key(digest: str) -> str:
    return f"{digest[:2]}/{digest}"


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
        storage_path = str(destination)
        if r2.configured():
            r2.put_object(_object_key(digest), destination.read_bytes())
            storage_path = f"r2://{r2.bucket()}/{_object_key(digest)}"
        return {
            "role": role, "original_name": file_storage.filename, "storage_path": storage_path,
            "sha256": digest, "size_bytes": size, "detected_type": detected,
        }
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _digest_from_path(storage_path: str) -> str | None:
    name = Path(storage_path).name
    if len(name) == 64 and all(c in "0123456789abcdef" for c in name):
        return name
    if storage_path.startswith("r2://"):
        return storage_path.rsplit("/", 1)[-1]
    return None


def _ensure_suffix(path: str, suffix: str) -> str:
    if not suffix:
        return path
    if not suffix.startswith("."):
        suffix = "." + suffix
    if path.endswith(suffix):
        return path
    linked = Path(path + suffix)
    if not linked.exists():
        try:
            os.link(path, linked)
        except OSError:
            linked.write_bytes(Path(path).read_bytes())
    return str(linked)


def materialize(storage_path: str, suffix: str = "") -> str:
    """解析器需要本地路径。R2 URI 或本地丢失时从 R2 拉回；可加 .step/.pdf 后缀。"""
    if storage_path.startswith("r2://"):
        _bucket, key = r2.parse_uri(storage_path)
        digest = key.rsplit("/", 1)[-1]
        cached = storage_root() / digest[:2] / digest
        if not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(r2.get_object(key))
        return _ensure_suffix(str(cached), suffix)
    local = Path(storage_path)
    if local.exists():
        return _ensure_suffix(str(local), suffix)
    digest = _digest_from_path(storage_path)
    if digest and r2.configured():
        cached = storage_root() / digest[:2] / digest
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(r2.get_object(f"{digest[:2]}/{digest}"))
        return _ensure_suffix(str(cached), suffix)
    raise FileNotFoundError(f"解析文件不存在: {storage_path}")
