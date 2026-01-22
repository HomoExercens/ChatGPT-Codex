from __future__ import annotations

import os


def _login_demo(api_client):
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_hide_clip_excludes_from_feed(api_client) -> None:
    headers = _login_demo(api_client)

    feed = api_client.get(
        "/api/clips/feed?mode=1v1&sort=new&algo=v2&limit=10", headers=headers
    )
    assert feed.status_code == 200
    items = feed.json().get("items") or []
    assert items, "expected at least one clip in feed"
    rid = items[0]["replay_id"]

    hide = api_client.post(f"/api/clips/{rid}/hide", headers=headers)
    assert hide.status_code == 200
    assert hide.json().get("hidden") is True

    feed2 = api_client.get(
        "/api/clips/feed?mode=1v1&sort=new&algo=v2&limit=10", headers=headers
    )
    assert feed2.status_code == 200
    ids2 = [it.get("replay_id") for it in (feed2.json().get("items") or [])]
    assert rid not in ids2


def test_report_and_ops_reports_admin_gate(api_client) -> None:
    headers = _login_demo(api_client)

    rep = api_client.post(
        "/api/reports",
        headers=headers,
        json={"target_type": "clip", "target_id": "r_test_seed", "reason": "spam"},
    )
    assert rep.status_code == 200
    report_id = rep.json().get("report_id")
    assert isinstance(report_id, str) and report_id

    # admin disabled by default
    r0 = api_client.get("/api/ops/reports")
    assert r0.status_code == 401

    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"

    r1 = api_client.get("/api/ops/reports", headers={"X-Admin-Token": "wrong"})
    assert r1.status_code == 401

    r2 = api_client.get("/api/ops/reports", headers={"X-Admin-Token": "admintest"})
    assert r2.status_code == 200
    items = r2.json().get("items") or []
    assert any(it.get("id") == report_id for it in items)
