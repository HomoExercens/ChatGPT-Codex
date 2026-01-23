from __future__ import annotations

import pytest


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


def test_beat_clip_endpoint_creates_reply_and_shows_in_share_landing(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    headers = _guest_headers(api_client)
    r = api_client.post(
        "/api/challenges/clip/r_test_seed/beat",
        headers=headers,
        json={"source": "share_landing"},
    )
    assert r.status_code == 200
    payload = r.json()
    assert str(payload.get("challenge_id") or "").startswith("ch_")
    match_id = str(payload.get("match_id") or "")
    assert match_id.startswith("m_")

    # Match should complete synchronously in fast mode.
    detail = api_client.get(f"/api/matches/{match_id}", headers=headers)
    assert detail.status_code == 200
    md = detail.json()
    assert md.get("queue_type") == "challenge"
    assert md.get("status") == "done"
    assert md.get("replay_id")
    assert md.get("challenge") and md["challenge"].get("target_replay_id") == "r_test_seed"

    # Replies should appear on the original clip share landing.
    share = api_client.get("/s/clip/r_test_seed?start=0.0&end=2.0")
    assert share.status_code == 200
    html = share.text
    assert "Replies" in html
    assert f'/s/clip/{md.get("replay_id")}' in html


def test_beat_clip_endpoint_dedupes_double_click(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    headers = _guest_headers(api_client)
    r1 = api_client.post(
        "/api/challenges/clip/r_test_seed/beat",
        headers=headers,
        json={"source": "share_landing"},
    )
    assert r1.status_code == 200
    p1 = r1.json()

    r2 = api_client.post(
        "/api/challenges/clip/r_test_seed/beat",
        headers=headers,
        json={"source": "share_landing"},
    )
    assert r2.status_code == 200
    p2 = r2.json()

    assert p2.get("match_id") == p1.get("match_id")
    assert p2.get("attempt_id") == p1.get("attempt_id")


def test_guest_challenge_accept_limited_to_one_per_day(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    headers = _guest_headers(api_client)

    c1 = api_client.post(
        "/api/challenges",
        headers=headers,
        json={"kind": "clip", "target_replay_id": "r_test_seed", "start": 0.0, "end": 2.0},
    )
    assert c1.status_code == 200
    cid1 = str(c1.json().get("challenge_id") or "")
    assert cid1.startswith("ch_")

    a1 = api_client.post(
        f"/api/challenges/{cid1}/accept",
        headers=headers,
        json={"seed_set_count": 1},
    )
    assert a1.status_code == 200

    c2 = api_client.post(
        "/api/challenges",
        headers=headers,
        json={"kind": "clip", "target_replay_id": "r_test_seed", "start": 0.0, "end": 2.0},
    )
    assert c2.status_code == 200
    cid2 = str(c2.json().get("challenge_id") or "")
    assert cid2.startswith("ch_")

    a2 = api_client.post(
        f"/api/challenges/{cid2}/accept",
        headers=headers,
        json={"seed_set_count": 1},
    )
    assert a2.status_code == 429
    detail = a2.json().get("detail") or {}
    assert isinstance(detail, dict)
    assert detail.get("error") == "challenge_rate_limited"

