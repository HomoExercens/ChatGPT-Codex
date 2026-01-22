from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import orjson


def test_clips_feed_trending_v2_prefers_conversions(api_client, seeded_db) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Event, Match, Replay, User, Wallet
    from neuroleague_api.storage import load_replay_json, save_replay_json

    settings = Settings()
    now = datetime.now(UTC)

    match_a = f"m_trend_v2_a_{uuid4().hex[:8]}"
    match_b = f"m_trend_v2_b_{uuid4().hex[:8]}"
    replay_a = f"r_trend_v2_a_{uuid4().hex[:8]}"
    replay_b = f"r_trend_v2_b_{uuid4().hex[:8]}"

    with SessionLocal() as session:
        seed_replay = session.get(Replay, "r_test_seed")
        assert seed_replay is not None
        payload = load_replay_json(artifact_path=seed_replay.artifact_path)
        digest = str(seed_replay.digest or payload.get("digest") or "")
        assert digest

        # Two fresh matches in the near-future so they are always in the oversampled candidate set.
        future = now + timedelta(days=1)
        session.add(
            Match(
                id=match_a,
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                seed_set_count=1,
                user_a_id="user_demo",
                user_b_id="bot_alpha",
                blueprint_a_id="bp_demo_1v1",
                blueprint_b_id="bp_bot_1v1",
                status="done",
                progress=100,
                result="A",
                elo_delta_a=0,
                elo_delta_b=0,
                created_at=future,
                finished_at=future,
            )
        )
        session.add(
            Match(
                id=match_b,
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                seed_set_count=1,
                user_a_id="user_demo",
                user_b_id="bot_alpha",
                blueprint_a_id="bp_demo_1v1",
                blueprint_b_id="bp_bot_1v1",
                status="done",
                progress=100,
                result="A",
                elo_delta_a=0,
                elo_delta_b=0,
                created_at=future + timedelta(seconds=1),
                finished_at=future + timedelta(seconds=1),
            )
        )

        path_a = save_replay_json(replay_id=replay_a, payload=payload)
        path_b = save_replay_json(replay_id=replay_b, payload=payload)
        session.add(
            Replay(
                id=replay_a,
                match_id=match_a,
                artifact_path=path_a,
                digest=digest,
                created_at=future,
            )
        )
        session.add(
            Replay(
                id=replay_b,
                match_id=match_b,
                artifact_path=path_b,
                digest=digest,
                created_at=future,
            )
        )

        # Create a small pool of unique users to avoid per-user/day dedupe.
        for i in range(1, 13):
            uid = f"user_evt_{i}"
            if session.get(User, uid) is None:
                session.add(
                    User(
                        id=uid,
                        username=None,
                        display_name=f"E{i}",
                        is_guest=True,
                        created_at=now,
                    )
                )
                session.add(Wallet(user_id=uid, tokens_balance=0))

        when = now - timedelta(hours=1)

        # replay_a: lots of views, no conversions
        for i in range(1, 11):
            session.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=f"user_evt_{i}",
                    type="clip_view",
                    payload_json=orjson.dumps(
                        {"replay_id": replay_a, "match_id": match_a}
                    ).decode("utf-8"),
                    created_at=when,
                )
            )

        # replay_b: fewer views but strong conversions (open_ranked + completion)
        for i in range(11, 13):
            uid = f"user_evt_{i}"
            session.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=uid,
                    type="clip_view",
                    payload_json=orjson.dumps(
                        {"replay_id": replay_b, "match_id": match_b}
                    ).decode("utf-8"),
                    created_at=when,
                )
            )
            session.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=uid,
                    type="clip_open_ranked",
                    payload_json=orjson.dumps(
                        {"replay_id": replay_b, "match_id": match_b}
                    ).decode("utf-8"),
                    created_at=when,
                )
            )
            session.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=uid,
                    type="clip_completion",
                    payload_json=orjson.dumps(
                        {"replay_id": replay_b, "match_id": match_b}
                    ).decode("utf-8"),
                    created_at=when,
                )
            )

        session.commit()

    resp = api_client.get(
        "/api/clips/feed?mode=1v1&sort=trending&algo=v2&limit=2",
        headers=headers,
    )
    assert resp.status_code == 200
    items = resp.json().get("items") or []
    assert len(items) >= 2
    assert items[0]["replay_id"] == replay_b
    assert items[1]["replay_id"] == replay_a
