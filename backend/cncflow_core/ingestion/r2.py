"""Cloudflare R2：S3 兼容 PUT/GET，仅用标准库。"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


class R2Error(RuntimeError):
    pass


def configured() -> bool:
    return all(os.environ.get(key) for key in (
        "CNCFLOW_R2_ACCOUNT_ID",
        "CNCFLOW_R2_ACCESS_KEY_ID",
        "CNCFLOW_R2_SECRET_ACCESS_KEY",
        "CNCFLOW_R2_BUCKET",
    ))


def bucket() -> str:
    return os.environ["CNCFLOW_R2_BUCKET"]


def _host() -> str:
    override = os.environ.get("CNCFLOW_R2_ENDPOINT")
    if override:
        return override.split("://", 1)[-1].rstrip("/")
    return f"{os.environ['CNCFLOW_R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def _scheme() -> str:
    override = os.environ.get("CNCFLOW_R2_ENDPOINT", "https://")
    return "http" if override.startswith("http://") else "https"


def _canonical_uri(key: str) -> str:
    encoded = "/".join(quote(part, safe="") for part in key.split("/"))
    return f"/{bucket()}/{encoded}"


def _sign(method: str, key: str, body: bytes, content_type: str | None) -> tuple[str, dict[str, str]]:
    access = os.environ["CNCFLOW_R2_ACCESS_KEY_ID"]
    secret = os.environ["CNCFLOW_R2_SECRET_ACCESS_KEY"]
    region = os.environ.get("CNCFLOW_R2_REGION", "auto")
    host = _host()
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_uri = _canonical_uri(key)
    header_items = []
    if content_type:
        header_items.append(("content-type", content_type))
    header_items.extend((
        ("host", host),
        ("x-amz-content-sha256", payload_hash),
        ("x-amz-date", amz_date),
    ))
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in header_items)
    signed_headers = ";".join(k for k, _ in header_items)
    canonical_request = "\n".join([
        method, canonical_uri, "", canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def keyed(key_bytes: bytes, msg: str) -> bytes:
        return hmac.new(key_bytes, msg.encode(), hashlib.sha256).digest()

    signing_key = keyed(
        keyed(keyed(keyed(("AWS4" + secret).encode(), date_stamp), region), "s3"),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
    if content_type:
        headers["Content-Type"] = content_type
    return f"{_scheme()}://{host}{canonical_uri}", headers


def _request(method: str, key: str, body: bytes = b"", content_type: str | None = None) -> bytes:
    url, headers = _sign(method, key, body, content_type)
    req = Request(url, data=body if method in {"PUT", "POST"} else None, method=method, headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            return resp.read()
    except HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(key) from exc
        raise R2Error(f"R2 {method} {key} failed: HTTP {exc.code}") from exc


def put_object(key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
    _request("PUT", key, body, content_type)


def get_object(key: str) -> bytes:
    return _request("GET", key)


def object_exists(key: str) -> bool:
    try:
        _request("HEAD", key)
        return True
    except FileNotFoundError:
        return False


def parse_uri(uri: str) -> tuple[str, str]:
    """r2://bucket/key -> (bucket, key)."""
    if not uri.startswith("r2://"):
        raise ValueError(f"不是 R2 URI: {uri}")
    rest = uri[5:]
    bucket_name, _, key = rest.partition("/")
    if not bucket_name or not key:
        raise ValueError(f"R2 URI 不完整: {uri}")
    return bucket_name, key
