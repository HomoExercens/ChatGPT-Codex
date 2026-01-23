from __future__ import annotations

import pytest


def _login_headers(api_client, *, username: str) -> dict[str, str]:
    login = api_client.post("/api/auth/login", json={"username": username})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token
    return {"Authorization": f"Bearer {token}"}


def _guest_headers(api_client) -> dict[str, str]:
    guest = api_client.post("/api/auth/guest")
    assert guest.status_code == 200
    token = guest.json()["access_token"]
    assert token
    return {"Authorization": f"Bearer {token}"}


def _clear_rate_limiter_state() -> None:
    # In-memory limiter state is shared across the test process.
    from neuroleague_api import rate_limit as rl

    rl._STATE.clear()  # type: ignore[attr-defined]


def test_auto_tune_creates_forked_blueprint(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    headers = _login_headers(api_client, username="demo")
    r = api_client.post(
        "/api/blueprints/bp_demo_1v1/auto_tune",
        headers=headers,
        json={"preset": "dps"},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("ok") is True
    assert payload.get("parent_blueprint_id") == "bp_demo_1v1"
    assert payload.get("preset") in {"dps", "tank", "speed"}

    bp = payload.get("blueprint") or {}
    assert str(bp.get("id") or "").startswith("bp_")
    assert bp.get("status") == "draft"
    assert bp.get("forked_from_id") == "bp_demo_1v1"
    assert bp.get("parent_blueprint_id") == "bp_demo_1v1"
    assert int(bp.get("fork_depth") or 0) >= 1


def test_auto_tune_requires_ownership(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    guest_headers = _guest_headers(api_client)
    r = api_client.post(
        "/api/blueprints/bp_demo_1v1/auto_tune",
        headers=guest_headers,
        json={"preset": "dps"},
    )
    assert r.status_code == 404


def test_auto_tune_rate_limited(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    monkeypatch.setenv("NEUROLEAGUE_RATE_LIMIT_BLUEPRINT_AUTO_TUNE_PER_MINUTE", "1")
    _clear_rate_limiter_state()

    headers = _login_headers(api_client, username="demo")
    r1 = api_client.post(
        "/api/blueprints/bp_demo_1v1/auto_tune",
        headers=headers,
        json={"preset": "dps"},
    )
    assert r1.status_code == 200

    r2 = api_client.post(
        "/api/blueprints/bp_demo_1v1/auto_tune",
        headers=headers,
        json={"preset": "dps"},
    )
    assert r2.status_code == 429

