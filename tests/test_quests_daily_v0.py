from __future__ import annotations

import pytest


def _login_headers(api_client, *, username: str) -> dict[str, str]:
    login = api_client.post("/api/auth/login", json={"username": username})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token
    return {"Authorization": f"Bearer {token}"}


def _clear_rate_limiter_state() -> None:
    # In-memory limiter state is shared across the test process.
    from neuroleague_api import rate_limit as rl

    rl._STATE.clear()  # type: ignore[attr-defined]


def test_daily_quest_claim_by_key(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    # Seed a minimal daily quest so selection is deterministic in the test DB.
    from datetime import UTC, datetime

    import orjson
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Quest

    with SessionLocal() as session:
        existing = session.query(Quest).filter(Quest.cadence == "daily", Quest.key == "share_reply_1").first()
        if existing is None:
            session.add(
                Quest(
                    id="q_daily_share_reply_1",
                    cadence="daily",
                    key="share_reply_1",
                    title="Share 1 reply",
                    description="Share a reply clip once.",
                    goal_count=1,
                    event_type="reply_clip_shared",
                    filters_json=orjson.dumps({}).decode("utf-8"),
                    reward_cosmetic_id="badge_quest_daily_share_reply_1",
                    reward_amount=1,
                    active_from=None,
                    active_to=None,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()

    headers = _login_headers(api_client, username="demo")

    ev = api_client.post(
        "/api/events/track",
        headers=headers,
        json={
            "type": "reply_clip_shared",
            "source": "test",
            "meta": {"reply_replay_id": "r_seed_002", "parent_replay_id": "r_seed_001"},
        },
    )
    assert ev.status_code == 200

    today = api_client.get("/api/quests/today", headers=headers)
    assert today.status_code == 200
    payload = today.json()
    daily = payload.get("daily") or []
    target = next((a for a in daily if (a.get("quest") or {}).get("key") == "share_reply_1"), None)
    assert target is not None
    assert bool(target.get("claimable")) is True

    claim = api_client.post("/api/quests/claim/share_reply_1", headers=headers)
    assert claim.status_code == 200
    out = claim.json()
    assert out.get("ok") is True
