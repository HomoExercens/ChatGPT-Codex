from __future__ import annotations


def _login_demo(api_client):
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_experiments_assignment_is_stable(api_client) -> None:
    headers = _login_demo(api_client)

    r1 = api_client.get(
        "/api/experiments/assign?keys=clips_feed_algo,share_cta_copy,quick_battle_default",
        headers=headers,
    )
    assert r1.status_code == 200
    a1 = r1.json()
    assert isinstance(a1, dict)
    assert "clips_feed_algo" in a1
    assert "share_cta_copy" in a1
    assert "quick_battle_default" in a1

    v1 = a1["clips_feed_algo"]["variant"]
    r2 = api_client.get(
        "/api/experiments/assign?keys=clips_feed_algo,share_cta_copy,quick_battle_default",
        headers=headers,
    )
    assert r2.status_code == 200
    a2 = r2.json()
    assert a2["clips_feed_algo"]["variant"] == v1
