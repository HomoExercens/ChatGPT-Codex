from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import orjson


def test_shorts_variants_primary_kpi_matches_ranked_done_rate() -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.growth_metrics import load_shorts_variants
    from neuroleague_api.models import Event

    now = datetime.now(UTC)
    match_id = f"m_pk_{uuid4().hex[:10]}"

    payload_base = {
        "source": "s/clip",
        "ip_hash": f"ip_{uuid4().hex}",
        "user_agent_hash": f"ua_{uuid4().hex}",
        "variants": {"clip_len_v1": "10s", "captions_v2": "A"},
    }

    with SessionLocal() as session:
        session.add(
            Event(
                id=f"ev_pk_share_{uuid4().hex}",
                user_id=None,
                type="share_open",
                payload_json=orjson.dumps(payload_base).decode("utf-8"),
                created_at=now,
            )
        )
        session.add(
            Event(
                id=f"ev_pk_rq_{uuid4().hex}",
                user_id=None,
                type="ranked_queue",
                payload_json=orjson.dumps({**payload_base, "match_id": match_id}).decode(
                    "utf-8"
                ),
                created_at=now,
            )
        )
        session.add(
            Event(
                id=f"ev_pk_rd_{uuid4().hex}",
                user_id=None,
                type="ranked_done",
                payload_json=orjson.dumps({"match_id": match_id}).decode("utf-8"),
                created_at=now,
            )
        )
        session.commit()

        data = load_shorts_variants(session, days=1)

    assert data.get("primary_kpi") == "ranked_done_per_share_open"

    tables = data.get("tables") or []
    clip_len = next(t for t in tables if t.get("key") == "clip_len_v1")
    row = next(r for r in (clip_len.get("variants") or []) if r.get("id") == "10s")
    assert row["primary_kpi_rate"] == row["ranked_done_rate"]
