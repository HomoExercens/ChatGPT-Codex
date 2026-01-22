from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from neuroleague_api.core.config import Settings


class StorageBackend(Protocol):
    def put_bytes(
        self, *, key: str, data: bytes, content_type: str | None = None
    ) -> None: ...
    def put_file(
        self, *, key: str, path: Path, content_type: str | None = None
    ) -> None: ...
    def get_bytes(self, *, key: str) -> bytes: ...
    def exists(self, *, key: str) -> bool: ...
    def delete(self, *, key: str) -> bool: ...
    def public_url(self, *, key: str) -> str: ...
    def local_path(self, *, key: str) -> Path | None: ...


def _validate_key(key: str) -> str:
    raw = str(key or "").strip()
    if not raw:
        raise ValueError("empty key")
    if raw.startswith("/"):
        raise ValueError("absolute key not allowed")
    if ".." in raw.split("/"):
        raise ValueError("path traversal not allowed")
    return raw.replace("\\", "/")


@dataclass(frozen=True)
class LocalFSBackend:
    root_dir: Path
    public_base_path: str = "/api/assets"

    def _abs(self, key: str) -> Path:
        key = _validate_key(key)
        root = self.root_dir.resolve()
        p = (root / key).resolve()
        if root != p and root not in p.parents:
            raise ValueError("key escapes artifacts root")
        return p

    def local_path(self, *, key: str) -> Path:
        return self._abs(key)

    def exists(self, *, key: str) -> bool:
        return self._abs(key).exists()

    def get_bytes(self, *, key: str) -> bytes:
        return self._abs(key).read_bytes()

    def delete(self, *, key: str) -> bool:
        p = self._abs(key)
        if not p.exists():
            return False
        if p.is_file():
            p.unlink(missing_ok=True)  # type: ignore[arg-type]
            return True
        return False

    def put_bytes(
        self, *, key: str, data: bytes, content_type: str | None = None
    ) -> None:
        dst = self._abs(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(dst)

    def put_file(
        self, *, key: str, path: Path, content_type: str | None = None
    ) -> None:
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(str(src))
        dst = self._abs(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        shutil.copyfile(src, tmp)
        tmp.replace(dst)

    def public_url(self, *, key: str) -> str:
        key = _validate_key(key)
        base = self.public_base_path.rstrip("/")
        return f"{base}/{quote(key)}"


@dataclass(frozen=True)
class S3Backend:
    bucket: str
    prefix: str = ""
    cdn_base_url: str | None = None
    public_base_path: str | None = None
    region: str | None = None
    endpoint_url: str | None = None

    def _full_key(self, key: str) -> str:
        key = _validate_key(key)
        pfx = (self.prefix or "").lstrip("/")
        if pfx and not pfx.endswith("/"):
            pfx += "/"
        return f"{pfx}{key}"

    def _client(self):
        try:
            import boto3  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "S3 backend selected but boto3 is not installed. Install `boto3`."
            ) from exc
        return boto3.client(
            "s3", region_name=self.region, endpoint_url=self.endpoint_url
        )

    def local_path(self, *, key: str) -> Path | None:
        return None

    def exists(self, *, key: str) -> bool:
        full = self._full_key(key)
        try:
            self._client().head_object(Bucket=self.bucket, Key=full)
        except Exception:  # noqa: BLE001
            return False
        return True

    def get_bytes(self, *, key: str) -> bytes:
        full = self._full_key(key)
        obj = self._client().get_object(Bucket=self.bucket, Key=full)
        body = obj.get("Body")
        if body is None:
            raise RuntimeError("S3 get_object missing Body")
        return body.read()

    def put_bytes(
        self, *, key: str, data: bytes, content_type: str | None = None
    ) -> None:
        full = self._full_key(key)
        args = {"Bucket": self.bucket, "Key": full, "Body": data}
        if content_type:
            args["ContentType"] = content_type
        self._client().put_object(**args)

    def put_file(
        self, *, key: str, path: Path, content_type: str | None = None
    ) -> None:
        full = self._full_key(key)
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client().upload_file(
            str(path), self.bucket, full, ExtraArgs=extra or None
        )

    def delete(self, *, key: str) -> bool:
        full = self._full_key(key)
        try:
            self._client().delete_object(Bucket=self.bucket, Key=full)
            return True
        except Exception:  # noqa: BLE001
            return False

    def public_url(self, *, key: str) -> str:
        full = self._full_key(key)
        if self.cdn_base_url:
            base = self.cdn_base_url.rstrip("/")
            return f"{base}/{quote(full)}"
        if self.public_base_path:
            base = str(self.public_base_path).rstrip("/")
            return f"{base}/{quote(full)}"
        return f"https://{self.bucket}.s3.amazonaws.com/{quote(full)}"


def guess_content_type(key: str) -> str:
    ct, _enc = mimetypes.guess_type(key)
    return ct or "application/octet-stream"


@lru_cache(maxsize=1)
def get_storage_backend() -> StorageBackend:
    settings = Settings()
    kind = str(settings.storage_backend or "local").lower()
    if kind == "s3":
        if not settings.storage_s3_bucket:
            raise RuntimeError(
                "NEUROLEAGUE_STORAGE_S3_BUCKET is required for s3 backend"
            )
        return S3Backend(
            bucket=settings.storage_s3_bucket,
            prefix=settings.storage_s3_prefix or "",
            cdn_base_url=settings.storage_cdn_base_url or None,
            public_base_path=str(settings.storage_public_base_path or "/api/assets"),
            region=settings.storage_s3_region or None,
            endpoint_url=settings.storage_s3_endpoint_url or None,
        )

    # Default: local filesystem under artifacts_dir.
    root = Path(settings.artifacts_dir)
    root.mkdir(parents=True, exist_ok=True)
    return LocalFSBackend(
        root_dir=root,
        public_base_path=str(settings.storage_public_base_path or "/api/assets"),
    )


def reset_storage_backend_cache() -> None:
    get_storage_backend.cache_clear()
