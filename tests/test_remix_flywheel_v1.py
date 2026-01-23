from __future__ import annotations

from datetime import UTC, datetime

import pytest


def _login_demo(api_client) -> dict[str, str]:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_blueprint_fork_creates_lineage_and_counts(api_client) -> None:
    headers = _login_demo(api_client)

    created = api_client.post(
        "/api/blueprints",
        headers=headers,
        json={"name": "Root", "mode": "1v1"},
    )
    assert created.status_code == 200
    root = created.json()
    root_id = str(root.get("id") or "")
    assert root_id.startswith("bp_")

    fork1 = api_client.post(
        f"/api/blueprints/{root_id}/fork",
        headers=headers,
        json={
            "name": "Fork 1",
            "source_replay_id": "r_test_seed",
            "source": "forge",
            "note": "test",
        },
    )
    assert fork1.status_code == 200
    b = fork1.json()
    b_id = str(b.get("id") or "")
    assert b.get("forked_from_id") == root_id
    assert b.get("fork_root_blueprint_id") == root_id
    assert int(b.get("fork_depth") or 0) == 1
    assert int(b.get("fork_count") or 0) == 0
    assert b.get("source_replay_id") == "r_test_seed"

    root_after_1 = api_client.get(f"/api/blueprints/{root_id}", headers=headers)
    assert root_after_1.status_code == 200
    assert int(root_after_1.json().get("fork_count") or 0) == 1

    fork2 = api_client.post(
        f"/api/blueprints/{b_id}/fork",
        headers=headers,
        json={"name": "Fork 2", "source": "forge"},
    )
    assert fork2.status_code == 200
    c = fork2.json()
    c_id = str(c.get("id") or "")
    assert c.get("forked_from_id") == b_id
    assert c.get("fork_root_blueprint_id") == root_id
    assert int(c.get("fork_depth") or 0) == 2

    root_after_2 = api_client.get(f"/api/blueprints/{root_id}", headers=headers)
    assert root_after_2.status_code == 200
    assert int(root_after_2.json().get("fork_count") or 0) == 2

    b_after_2 = api_client.get(f"/api/blueprints/{b_id}", headers=headers)
    assert b_after_2.status_code == 200
    assert int(b_after_2.json().get("fork_count") or 0) == 1

    lineage = api_client.get(f"/api/blueprints/{c_id}/lineage", headers=headers)
    assert lineage.status_code == 200
    payload = lineage.json()
    assert payload.get("blueprint_id") == c_id
    assert isinstance(payload.get("chain"), list)
    assert isinstance(payload.get("children"), list)
    assert isinstance(payload.get("ancestors"), list)
    assert isinstance(payload.get("root"), dict)
    assert isinstance(payload.get("self"), dict)
    assert payload["root"]["blueprint_id"] == root_id
    assert payload["self"]["blueprint_id"] == c_id
    assert int(payload.get("fork_depth") or 0) == 2

    chain = payload.get("chain") or []
    assert len(chain) >= 3
    assert chain[0]["blueprint_id"] == c_id
    assert chain[1]["blueprint_id"] == b_id
    assert chain[2]["blueprint_id"] == root_id

    ancestors = payload.get("ancestors") or []
    assert len(ancestors) >= 2
    assert ancestors[0]["blueprint_id"] == root_id
    assert ancestors[-1]["blueprint_id"] == b_id


def test_blueprint_fork_missing_and_permission(api_client) -> None:
    headers = _login_demo(api_client)

    missing = api_client.post("/api/blueprints/bp_missing_404/fork", headers=headers, json={})
    assert missing.status_code == 404

    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Blueprint, User, Wallet
    from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
    from neuroleague_sim.models import BlueprintSpec

    settings = Settings()
    now = datetime.now(UTC)

    other_id = "user_other_v1"
    other_bp_id = "bp_other_draft_v1"
    with SessionLocal() as session:
        if session.get(User, other_id) is None:
            session.add(User(id=other_id, username=None, display_name="Other", is_guest=True, created_at=now))
            session.add(Wallet(user_id=other_id, tokens_balance=0))

        spec = BlueprintSpec(
            mode="1v1",
            team=[{"creature_id": "ember_fox", "formation": "front", "items": {}}],
        )
        session.add(
            Blueprint(
                id=other_bp_id,
                user_id=other_id,
                name="Other Draft",
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                status="draft",
                spec_json=canonical_json_bytes(spec.model_dump()).decode("utf-8"),
                spec_hash=canonical_sha256(spec.model_dump()),
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    denied = api_client.post(f"/api/blueprints/{other_bp_id}/fork", headers=headers, json={})
    assert denied.status_code == 404


def test_blueprint_fork_rate_limited(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_RATE_LIMIT_BLUEPRINT_FORK_PER_MINUTE", "1")
    monkeypatch.setenv("NEUROLEAGUE_RATE_LIMIT_BLUEPRINT_FORK_PER_HOUR", "999")
    monkeypatch.setenv("NEUROLEAGUE_RATE_LIMIT_BLUEPRINT_FORK_PER_MINUTE_IP", "999")
    monkeypatch.setenv("NEUROLEAGUE_RATE_LIMIT_BLUEPRINT_FORK_PER_HOUR_IP", "999")

    # Reset in-memory limiter state (shared across test process).
    from neuroleague_api import rate_limit as rl

    rl._STATE.clear()  # type: ignore[attr-defined]

    headers = _login_demo(api_client)
    created = api_client.post(
        "/api/blueprints",
        headers=headers,
        json={"name": "RateLimitRoot", "mode": "1v1"},
    )
    assert created.status_code == 200
    root_id = str(created.json().get("id") or "")
    assert root_id.startswith("bp_")

    ok = api_client.post(f"/api/blueprints/{root_id}/fork", headers=headers, json={})
    assert ok.status_code == 200

    limited = api_client.post(f"/api/blueprints/{root_id}/fork", headers=headers, json={})
    assert limited.status_code == 429
    detail = limited.json().get("detail") or {}
    assert isinstance(detail, dict)
    assert detail.get("error") == "rate_limited"
