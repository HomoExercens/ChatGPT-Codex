from __future__ import annotations

import hashlib


def derive_challenge_match_id(
    *, challenge_id: str, challenger_id: str, attempt_index: int
) -> str:
    raw = f"{str(challenge_id)}|{str(challenger_id)}|{int(attempt_index)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"m_ch_{digest[:16]}"
