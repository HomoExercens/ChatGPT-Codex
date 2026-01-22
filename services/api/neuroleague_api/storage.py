from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import orjson

from neuroleague_api.core.config import Settings
from neuroleague_api.storage_backend import get_storage_backend


def ensure_artifacts_dir() -> Path:
    settings = Settings()
    path = Path(settings.artifacts_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "replays").mkdir(parents=True, exist_ok=True)
    (path / "sharecards").mkdir(parents=True, exist_ok=True)
    (path / "clips").mkdir(parents=True, exist_ok=True)
    (path / "ops").mkdir(parents=True, exist_ok=True)
    return path


def save_replay_json(*, replay_id: str, payload: dict[str, Any]) -> str:
    ensure_artifacts_dir()
    key = os.path.join("replays", f"{replay_id}.json").replace("\\", "/")
    data = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    backend = get_storage_backend()
    backend.put_bytes(key=key, data=data, content_type="application/json")
    return key


def load_replay_json(*, artifact_path: str) -> dict[str, Any]:
    backend = get_storage_backend()
    p = resolve_local_artifact_path(artifact_path)
    if p is not None and p.exists():
        return orjson.loads(p.read_bytes())
    # Treat as a storage key.
    return orjson.loads(backend.get_bytes(key=_normalize_key(artifact_path)))


def resolve_local_artifact_path(artifact_path: str) -> Path | None:
    settings = Settings()
    backend = get_storage_backend()
    local_root = Path(settings.artifacts_dir)
    local = backend.local_path(key="ops/.probe")  # type: ignore[arg-type]
    if local is None:
        return None

    raw = str(artifact_path or "").strip()
    if not raw:
        return None
    norm = raw.replace("\\", "/")
    if Path(norm).is_absolute():
        return Path(norm)

    # If stored as "artifacts/..." (legacy), map onto the configured artifacts_dir.
    stripped = norm[2:] if norm.startswith("./") else norm
    art_name = Path(settings.artifacts_dir).name or "artifacts"
    if stripped == art_name:
        return local_root
    if stripped.startswith(f"{art_name}/"):
        suffix = stripped[len(f"{art_name}/") :]
        return local_root / suffix

    # If it looks like a key ("clips/...", "sharecards/..."), resolve under artifacts_dir.
    return backend.local_path(key=_normalize_key(norm))


def _normalize_key(key: str) -> str:
    return str(key or "").strip().replace("\\", "/").lstrip("/")
