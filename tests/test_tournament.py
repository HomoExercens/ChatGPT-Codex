from __future__ import annotations

from datetime import UTC, datetime


def test_tournament_leaderboard_and_me(api_client, seeded_db) -> None:
    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Blueprint, Match, User
    from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
    from neuroleague_sim.models import BlueprintSpec

    settings = Settings()
    now = datetime.now(UTC)
    week_id = "2026W01"

    # Insert an extra human user with a submitted blueprint.
    spec = BlueprintSpec(
        mode="1v1",
        team=[{"creature_id": "slime_knight", "formation": "front", "items": {}}],
    )
    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())

    with SessionLocal() as session:
        if not session.get(User, "user_tour_alice"):
            session.add(
                User(
                    id="user_tour_alice",
                    username="tour_alice",
                    display_name="Tour Alice",
                    is_guest=False,
                    created_at=now,
                )
            )
        if not session.get(Blueprint, "bp_tour_alice_1v1"):
            session.add(
                Blueprint(
                    id="bp_tour_alice_1v1",
                    user_id="user_tour_alice",
                    name="Tour Alice Build",
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

        # Demo: win + draw => 4 points.
        session.add(
            Match(
                id="m_tour_1",
                queue_type="tournament",
                week_id=week_id,
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
                created_at=now,
                finished_at=now,
            )
        )
        session.add(
            Match(
                id="m_tour_2",
                queue_type="tournament",
                week_id=week_id,
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                seed_set_count=1,
                user_a_id="user_demo",
                user_b_id="bot_alpha",
                blueprint_a_id="bp_demo_1v1",
                blueprint_b_id="bp_bot_1v1",
                status="done",
                progress=100,
                result="draw",
                elo_delta_a=0,
                elo_delta_b=0,
                created_at=now,
                finished_at=now,
            )
        )

        # Alice: one win => 3 points.
        session.add(
            Match(
                id="m_tour_3",
                queue_type="tournament",
                week_id=week_id,
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                seed_set_count=1,
                user_a_id="user_tour_alice",
                user_b_id="bot_alpha",
                blueprint_a_id="bp_tour_alice_1v1",
                blueprint_b_id="bp_bot_1v1",
                status="done",
                progress=100,
                result="A",
                elo_delta_a=0,
                elo_delta_b=0,
                created_at=now,
                finished_at=now,
            )
        )
        session.commit()

    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    lb = api_client.get(
        f"/api/tournament/leaderboard?week_id={week_id}&mode=1v1&limit=10",
        headers=headers,
    )
    assert lb.status_code == 200
    rows = lb.json()
    assert rows[0]["user_id"] == "user_demo"
    assert rows[0]["points"] == 4

    me = api_client.get(
        f"/api/tournament/me?week_id={week_id}&mode=1v1", headers=headers
    )
    assert me.status_code == 200
    me_payload = me.json()
    assert me_payload["points"] == 4
    assert me_payload["rank"] == 1
