from __future__ import annotations


def test_ops_balance_latest_shape(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = api_client.get("/api/ops/balance/latest?mode=1v1", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["mode"] == "1v1"
    assert "data" in payload
    assert "items" in payload["data"]
    assert isinstance(payload["data"]["items"], list)
