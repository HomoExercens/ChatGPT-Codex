from __future__ import annotations


def _guest_token(api_client) -> str:
    resp = api_client.post("/api/auth/guest", json={"method": "direct"})
    assert resp.status_code == 200
    token = resp.json().get("access_token")
    assert isinstance(token, str) and token
    return token


def test_demo_presets_and_run_are_idempotent(api_client) -> None:
    presets = api_client.get("/api/demo/presets")
    assert presets.status_code == 200
    ids = [p.get("id") for p in presets.json()]
    assert set(ids) >= {"mech", "storm", "void"}

    token = _guest_token(api_client)
    headers = {"Authorization": f"Bearer {token}"}

    run1 = api_client.post("/api/demo/run", json={"preset_id": "mech"}, headers=headers)
    assert run1.status_code == 200
    out1 = run1.json()
    assert out1.get("match_id", "").startswith("m_demo_mech_")
    assert out1.get("replay_id", "").startswith("r_demo_mech_")
    assert out1.get("challenge_id", "").startswith("ch_demo_mech_")
    assert "/s/clip/" in str(out1.get("share_url", ""))
    assert "/kit.zip?start=" in str(out1.get("kit_url", ""))

    run2 = api_client.post("/api/demo/run", json={"preset_id": "mech"}, headers=headers)
    assert run2.status_code == 200
    out2 = run2.json()

    assert out2.get("match_id") == out1.get("match_id")
    assert out2.get("replay_id") == out1.get("replay_id")
    assert out2.get("challenge_id") == out1.get("challenge_id")

    m = api_client.get(f"/api/matches/{out1['match_id']}", headers=headers)
    assert m.status_code == 200
    assert m.json().get("status") == "done"
