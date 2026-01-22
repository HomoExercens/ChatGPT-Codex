from __future__ import annotations

from datetime import UTC, datetime, timedelta

import orjson


def test_blueprint_submit_cooldown_429_and_event(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    a = api_client.post(
        "/api/blueprints", headers=headers, json={"name": "A", "mode": "1v1"}
    )
    assert a.status_code == 200
    a_id = a.json()["id"]
    submit_a = api_client.post(f"/api/blueprints/{a_id}/submit", headers=headers)
    assert submit_a.status_code == 200

    b = api_client.post(
        "/api/blueprints", headers=headers, json={"name": "B", "mode": "1v1"}
    )
    assert b.status_code == 200
    b_id = b.json()["id"]
    submit_b = api_client.post(f"/api/blueprints/{b_id}/submit", headers=headers)
    assert submit_b.status_code == 429
    detail = submit_b.json().get("detail") or {}
    assert detail.get("error") == "submit_cooldown"
    assert int(detail.get("retry_after_sec") or 0) > 0
    assert int(submit_b.headers.get("Retry-After") or 0) == int(
        detail.get("retry_after_sec") or 0
    )

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Event

    with SessionLocal() as session:
        events = session.query(Event).filter(Event.user_id == "user_demo").all()
        flagged = []
        for e in events:
            if e.type != "anti_abuse_flag":
                continue
            payload = {}
            try:
                payload = orjson.loads(e.payload_json)
            except Exception:  # noqa: BLE001
                payload = {}
            if payload.get("reason") == "submit_cooldown":
                flagged.append(payload)
        assert flagged, "expected anti_abuse_flag event for submit_cooldown"


def test_matchmaking_repeat_penalty_avoids_recent_opponent(seeded_db) -> None:
    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Blueprint, Match, Rating, User
    from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
    from neuroleague_sim.models import BlueprintSpec
    from neuroleague_api.routers.matches import _pick_human_opponent_blueprint

    settings = Settings()
    now = datetime.now(UTC)

    spec = BlueprintSpec(
        mode="1v1",
        team=[
            {"creature_id": "slime_knight", "formation": "front", "items": {}},
        ],
    )
    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())

    with SessionLocal() as session:
        alice = User(
            id="user_alice2",
            username="alice2",
            display_name="Alice2",
            is_guest=False,
            created_at=now,
        )
        bob = User(
            id="user_bob2",
            username="bob2",
            display_name="Bob2",
            is_guest=False,
            created_at=now,
        )
        session.add(alice)
        session.add(bob)
        session.add(
            Rating(
                user_id=alice.id, mode="1v1", elo=1000, games_played=10, updated_at=now
            )
        )
        session.add(
            Rating(
                user_id=bob.id, mode="1v1", elo=1000, games_played=10, updated_at=now
            )
        )
        session.add(
            Blueprint(
                id="bp_alice2_1v1",
                user_id=alice.id,
                name="Alice2 build",
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                status="submitted",
                spec_json=spec_json,
                spec_hash=spec_hash,
                meta_json="{}",
                submitted_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Blueprint(
                id="bp_bob2_1v1",
                user_id=bob.id,
                name="Bob2 build",
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                status="submitted",
                spec_json=spec_json,
                spec_hash=spec_hash,
                meta_json="{}",
                submitted_at=now,
                created_at=now,
                updated_at=now,
            )
        )

        # Recent matches: demo played Alice2 repeatedly.
        for i in range(3):
            session.add(
                Match(
                    id=f"m_repeat_{i}",
                    mode="1v1",
                    ruleset_version=settings.ruleset_version,
                    seed_set_count=1,
                    user_a_id="user_demo",
                    user_b_id=alice.id,
                    blueprint_a_id="bp_demo_1v1",
                    blueprint_b_id="bp_alice2_1v1",
                    status="done",
                    progress=100,
                    result="A",
                    elo_delta_a=0,
                    elo_delta_b=0,
                    created_at=now + timedelta(seconds=i + 1),
                    finished_at=now + timedelta(seconds=i + 1),
                )
            )

        session.commit()

        opp_bp, _ = _pick_human_opponent_blueprint(
            session,
            mode="1v1",
            ruleset_version=settings.ruleset_version,
            match_id="m_fixed_repeat_test",
            player_user_id="user_demo",
            player_elo=1000,
        )
        assert opp_bp.user_id == bob.id
