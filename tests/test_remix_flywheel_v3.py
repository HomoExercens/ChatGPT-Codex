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


def _beat_clip_as_guest(api_client) -> tuple[str, str, dict[str, str]]:
    headers = _guest_headers(api_client)
    r = api_client.post(
        "/api/challenges/clip/r_test_seed/beat",
        headers=headers,
        json={"source": "test_v3"},
    )
    assert r.status_code == 200
    match_id = str(r.json().get("match_id") or "")
    assert match_id.startswith("m_")

    detail = api_client.get(f"/api/matches/{match_id}", headers=headers)
    assert detail.status_code == 200
    replay_id = str(detail.json().get("replay_id") or "")
    assert replay_id.startswith("r_")
    return match_id, replay_id, headers


def test_share_landing_shows_quick_remix_ctas(api_client) -> None:
    resp = api_client.get("/s/clip/r_test_seed?start=0.0&end=2.0")
    assert resp.status_code == 200
    html = resp.text
    assert "Quick Remix" in html
    assert "Beat This" in html


def test_replies_api_returns_reply_items(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    _match_id, reply_replay_id, headers = _beat_clip_as_guest(api_client)

    r = api_client.get(
        "/api/clips/r_test_seed/replies?sort=top&limit=12",
        headers=headers,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("sort") == "top"
    assert payload.get("algo_variant") in {"control", "variant_a"}
    items = payload.get("items") or []
    assert isinstance(items, list) and items
    assert any(str(it.get("reply_replay_id")) == reply_replay_id for it in items)

    first = items[0]
    assert isinstance(first.get("reactions"), dict)
    assert set(first["reactions"].keys()) >= {"up", "lol", "wow", "total"}
    assert isinstance(first.get("lineage"), dict)
    assert "fork_depth" in first["lineage"]


def test_reactions_endpoint_is_idempotent_per_actor(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    _match_id, reply_replay_id, headers = _beat_clip_as_guest(api_client)
    headers = {**headers, "x-device-id": "dev_test_rx_v3"}

    r0 = api_client.get(f"/api/clips/{reply_replay_id}/reactions", headers=headers)
    assert r0.status_code == 200
    assert int(r0.json().get("total") or 0) == 0

    r1 = api_client.post(
        f"/api/clips/{reply_replay_id}/react",
        headers=headers,
        json={"reaction_type": "up", "source": "test"},
    )
    assert r1.status_code == 200
    c1 = r1.json().get("counts") or {}
    assert int(c1.get("up") or 0) == 1
    assert int(c1.get("total") or 0) == 1

    # Same actor + type is deduped.
    r2 = api_client.post(
        f"/api/clips/{reply_replay_id}/react",
        headers=headers,
        json={"reaction_type": "up", "source": "test"},
    )
    assert r2.status_code == 200
    c2 = r2.json().get("counts") or {}
    assert int(c2.get("up") or 0) == 1
    assert int(c2.get("total") or 0) == 1

    # Different type counts.
    r3 = api_client.post(
        f"/api/clips/{reply_replay_id}/react",
        headers=headers,
        json={"reaction_type": "lol", "source": "test"},
    )
    assert r3.status_code == 200
    c3 = r3.json().get("counts") or {}
    assert int(c3.get("lol") or 0) == 1
    assert int(c3.get("total") or 0) == 2


def test_notifications_list_and_mark_read(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    _match_id, reply_replay_id, _headers = _beat_clip_as_guest(api_client)

    demo_headers = _login_headers(api_client, username="demo")
    resp = api_client.get("/api/notifications?limit=20", headers=demo_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert int(data.get("unread_count") or 0) >= 1
    items = data.get("items") or []
    assert isinstance(items, list) and items

    # Look for the notification linked to this reply (best-effort; multiple notifications may exist).
    target = None
    for it in items:
        meta = it.get("meta") or {}
        if str(meta.get("reply_replay_id") or "") == reply_replay_id:
            target = it
            break
    if target is None:
        target = items[0]

    nid = str(target.get("id") or "")
    assert nid
    before = int(data.get("unread_count") or 0)

    r2 = api_client.post(f"/api/notifications/{nid}/read", headers=demo_headers)
    assert r2.status_code == 200
    after = int(r2.json().get("unread_count") or 0)
    assert after <= before


def test_quick_remix_creates_draft_and_can_start_challenge(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_E2E_FAST", "1")
    _clear_rate_limiter_state()

    demo_headers = _login_headers(api_client, username="demo")

    qr = api_client.post(
        "/api/challenges/clip/r_test_seed/quick_remix",
        headers=demo_headers,
        json={"preset_id": "damage", "source": "test_v3"},
    )
    assert qr.status_code == 200
    qrj = qr.json()
    bp_id = str(qrj.get("blueprint_id") or "")
    parent_id = str(qrj.get("parent_blueprint_id") or "")
    assert bp_id.startswith("bp_")
    assert parent_id.startswith("bp_")

    beat = api_client.post(
        "/api/challenges/clip/r_test_seed/beat",
        headers=demo_headers,
        json={"source": "quick_remix_test", "blueprint_id": bp_id},
    )
    assert beat.status_code == 200
    match_id = str(beat.json().get("match_id") or "")
    assert match_id.startswith("m_")

    detail = api_client.get(f"/api/matches/{match_id}", headers=demo_headers)
    assert detail.status_code == 200
    md = detail.json()
    assert md.get("queue_type") == "challenge"
    assert md.get("status") == "done"
    assert md.get("replay_id")

