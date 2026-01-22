from __future__ import annotations

import base64
import hashlib
import zlib
from typing import Any

import orjson

from neuroleague_sim.canonical import canonical_json_bytes
from neuroleague_sim.models import BlueprintSpec


PREFIX_V1 = "NL1_"
MAX_CODE_LEN = 32_768
MAX_DECOMPRESSED_BYTES = 128_000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode(data + pad)


def encode_build_code(*, spec: BlueprintSpec, pack_hash: str | None = None) -> str:
    payload = {
        "v": 1,
        "ruleset_version": spec.ruleset_version,
        **({"pack_hash": str(pack_hash)} if pack_hash else {}),
        "mode": spec.mode,
        "spec": spec.model_dump(),
    }
    json_bytes = canonical_json_bytes(payload)
    compressed = zlib.compress(json_bytes, level=9)
    checksum = hashlib.sha256(json_bytes).hexdigest()[:8]
    return f"{PREFIX_V1}{_b64url_encode(compressed)}.{checksum}"


def decode_build_code_payload(*, build_code: str) -> dict[str, Any]:
    raw = str(build_code or "").strip()
    if not raw.startswith(PREFIX_V1):
        raise ValueError("unsupported build code prefix")
    if len(raw) > MAX_CODE_LEN:
        raise ValueError("build code too long")

    body = raw[len(PREFIX_V1) :]
    if "." not in body:
        raise ValueError("invalid build code format")
    b64, checksum = body.rsplit(".", 1)
    if not b64 or not checksum:
        raise ValueError("invalid build code format")

    compressed = _b64url_decode(b64)
    try:
        decomp = zlib.decompressobj()
        json_bytes = decomp.decompress(compressed, MAX_DECOMPRESSED_BYTES + 1)
        if len(json_bytes) <= MAX_DECOMPRESSED_BYTES:
            json_bytes += decomp.flush(MAX_DECOMPRESSED_BYTES + 1 - len(json_bytes))
        if decomp.unconsumed_tail:
            raise ValueError("build code payload too large")
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("build code payload invalid") from exc
    if len(json_bytes) > MAX_DECOMPRESSED_BYTES:
        raise ValueError("build code payload too large")
    if hashlib.sha256(json_bytes).hexdigest()[:8] != checksum:
        raise ValueError("build code checksum mismatch")

    payload: dict[str, Any] = orjson.loads(json_bytes)
    if not isinstance(payload, dict):
        raise ValueError("build code payload invalid")
    return payload


def decode_build_code(*, build_code: str) -> BlueprintSpec:
    payload = decode_build_code_payload(build_code=build_code)
    spec = payload.get("spec")
    return BlueprintSpec.model_validate(spec)


def build_code_hash(*, build_code: str) -> str:
    raw = str(build_code or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
