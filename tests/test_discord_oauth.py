from __future__ import annotations

import os


def test_discord_oauth_mock_login_flow(api_client) -> None:
    os.environ["NEUROLEAGUE_DISCORD_OAUTH_MOCK"] = "true"

    start = api_client.get("/api/auth/discord/start?format=json&next=/home")
    assert start.status_code == 200
    authorize_url = start.json().get("authorize_url")
    assert isinstance(authorize_url, str)
    assert "/api/auth/discord/callback" in authorize_url

    cb = api_client.get(
        "/api/auth/discord/callback",
        params={
            "code": "mock",
            "state": authorize_url.split("state=")[-1],
            "format": "json",
            "mock_id": "alpha",
        },
    )
    assert cb.status_code == 200
    token = cb.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = api_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json().get("is_guest") is False
    assert me.json().get("discord_connected") is True


def test_discord_oauth_mock_links_guest(api_client) -> None:
    os.environ["NEUROLEAGUE_DISCORD_OAUTH_MOCK"] = "true"

    guest = api_client.post("/api/auth/guest", json={"method": "direct"})
    assert guest.status_code == 200
    guest_token = guest.json()["access_token"]

    start = api_client.get(
        "/api/auth/discord/start",
        params={"format": "json", "next": "/home"},
        headers={"Authorization": f"Bearer {guest_token}"},
    )
    assert start.status_code == 200
    authorize_url = start.json().get("authorize_url")
    assert isinstance(authorize_url, str)

    state = authorize_url.split("state=")[-1]
    cb = api_client.get(
        "/api/auth/discord/callback",
        params={
            "code": "mock",
            "state": state,
            "format": "json",
            "mock_id": "guestlink",
        },
    )
    assert cb.status_code == 200
    assert cb.json()["merged_from_guest"] is False
    token = cb.json()["access_token"]
    me = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json().get("is_guest") is False
