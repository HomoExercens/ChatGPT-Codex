from __future__ import annotations


def test_events_track_accepts_wishlist_and_discord(api_client) -> None:
    guest = api_client.post("/api/auth/guest")
    assert guest.status_code == 200
    token = guest.json()["access_token"]
    assert token

    headers = {"Authorization": f"Bearer {token}"}

    for typ, meta in [
        ("wishlist_click", {"path": "steam", "app_id": "480"}),
        ("discord_click", {"url": "https://discord.com/"}),
    ]:
        resp = api_client.post(
            "/api/events/track",
            headers=headers,
            json={"type": typ, "source": "test", "meta": meta},
        )
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

