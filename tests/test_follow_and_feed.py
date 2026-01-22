from __future__ import annotations

from datetime import UTC, datetime

import orjson


def test_follow_toggle_and_activity_feed(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r1 = api_client.post("/api/users/bot_alpha/follow", headers=headers)
    assert r1.status_code == 200
    assert r1.json().get("following") is True

    # Inject one activity from the followed user.
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Event

    now = datetime.now(UTC)
    with SessionLocal() as session:
        session.add(
            Event(
                id="ev_follow_feed_test",
                user_id="bot_alpha",
                type="ranked_done",
                payload_json=orjson.dumps(
                    {"match_id": "m_test_seed", "mode": "1v1"}
                ).decode("utf-8"),
                created_at=now,
            )
        )
        session.commit()

    feed = api_client.get("/api/feed/activity?limit=10", headers=headers)
    assert feed.status_code == 200
    items = feed.json().get("items")
    assert isinstance(items, list)
    assert any(it.get("type") == "ranked_done" for it in items)

    r2 = api_client.post("/api/users/bot_alpha/follow", headers=headers)
    assert r2.status_code == 200
    assert r2.json().get("following") is False
