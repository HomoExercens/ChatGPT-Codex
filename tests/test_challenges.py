from __future__ import annotations

from neuroleague_api.challenges import derive_challenge_match_id


def _login_demo(api_client):
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_challenge_match_id_derivation_is_stable() -> None:
    m1 = derive_challenge_match_id(
        challenge_id="ch_abc",
        challenger_id="guest_123",
        attempt_index=1,
    )
    m2 = derive_challenge_match_id(
        challenge_id="ch_abc",
        challenger_id="guest_123",
        attempt_index=1,
    )
    m3 = derive_challenge_match_id(
        challenge_id="ch_abc",
        challenger_id="guest_123",
        attempt_index=2,
    )
    assert m1 == m2
    assert m1 != m3


def test_create_and_get_challenge_build(api_client) -> None:
    headers = _login_demo(api_client)
    r = api_client.post(
        "/api/challenges",
        headers=headers,
        json={
            "kind": "build",
            "target_blueprint_id": "bp_bot_1v1",
            "start": 0,
            "end": 6.0,
        },
    )
    assert r.status_code == 200
    payload = r.json()
    cid = payload.get("challenge_id")
    assert isinstance(cid, str) and cid.startswith("ch_")
    assert payload.get("share_url", "").startswith("/s/challenge/")

    g = api_client.get(f"/api/challenges/{cid}", headers=headers)
    assert g.status_code == 200
    g2 = g.json()
    assert g2.get("id") == cid
    assert g2.get("kind") == "build"


def test_create_and_get_challenge_clip(api_client) -> None:
    headers = _login_demo(api_client)
    r = api_client.post(
        "/api/challenges",
        headers=headers,
        json={
            "kind": "clip",
            "target_replay_id": "r_test_seed",
            "start": 0,
            "end": 6.0,
        },
    )
    assert r.status_code == 200
    cid = r.json().get("challenge_id")
    assert isinstance(cid, str) and cid.startswith("ch_")
    g = api_client.get(f"/api/challenges/{cid}", headers=headers)
    assert g.status_code == 200
    assert g.json().get("kind") == "clip"
