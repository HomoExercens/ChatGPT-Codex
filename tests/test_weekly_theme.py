from __future__ import annotations


def test_weekly_theme_has_portals_and_augments(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = api_client.get("/api/meta/weekly?week_id=2026W01", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("week_id") == "2026W01"

    portals = payload.get("featured_portals") or []
    augments = payload.get("featured_augments") or []
    assert isinstance(portals, list) and len(portals) >= 1
    assert isinstance(augments, list) and len(augments) >= 6

    tiers = {int(a.get("tier") or 0) for a in augments if isinstance(a, dict)}
    assert {1, 2, 3}.issubset(tiers)
