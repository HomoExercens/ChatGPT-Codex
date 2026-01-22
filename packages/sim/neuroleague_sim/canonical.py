from __future__ import annotations

import hashlib
from typing import Any

import orjson


def canonical_json_bytes(obj: Any) -> bytes:
    return orjson.dumps(obj, option=orjson.OPT_SORT_KEYS)


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()
