from __future__ import annotations

import hashlib


def derive_seed(match_id: str, seed_index: int | str) -> int:
    msg = f"{match_id}:{seed_index}".encode("utf-8")
    digest = hashlib.sha256(msg).digest()
    return int.from_bytes(digest[:8], "little", signed=False) % (2**32)
