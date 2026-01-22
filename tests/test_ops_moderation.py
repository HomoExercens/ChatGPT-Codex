from __future__ import annotations


def test_ops_moderation_resolve_hide_and_soft_ban(monkeypatch, seeded_db) -> None:
    monkeypatch.setenv("NEUROLEAGUE_ADMIN_TOKEN", "admin-token")

    from fastapi.testclient import TestClient

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.main import create_app
    from neuroleague_api.models import ModerationHide, Report, UserSoftBan

    client = TestClient(create_app())

    login = client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    rep = client.post(
        "/api/reports",
        json={"target_type": "clip", "target_id": "r_test_seed", "reason": "spam"},
        headers=headers,
    )
    assert rep.status_code == 200
    report_id = rep.json()["report_id"]

    ops_headers = {"X-Admin-Token": "admin-token"}
    listed = client.get("/api/ops/reports?status=open&limit=20", headers=ops_headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(r["id"] == report_id and r["status"] == "open" for r in items)

    resolved = client.post(f"/api/ops/reports/{report_id}/resolve", headers=ops_headers)
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    hide = client.post(
        "/api/ops/moderation/hide_target",
        json={"target_type": "clip", "target_id": "r_test_seed", "reason": "test hide"},
        headers=ops_headers,
    )
    assert hide.status_code == 200

    feed = client.get(
        "/api/clips/feed?mode=1v1&sort=trending&limit=10", headers=headers
    )
    assert feed.status_code == 200
    assert all(
        it.get("replay_id") != "r_test_seed" for it in (feed.json().get("items") or [])
    )

    ban = client.post(
        "/api/ops/moderation/soft_ban_user",
        json={"user_id": "user_demo", "duration_hours": 1, "reason": "test ban"},
        headers=ops_headers,
    )
    assert ban.status_code == 200

    blocked = client.post(
        "/api/matches/m_test_seed/sharecard_jobs",
        json={"theme": "dark", "locale": "en"},
        headers=headers,
    )
    assert blocked.status_code == 403
    assert "soft_banned" in blocked.text

    # Cleanup (seeded_db is shared across tests).
    with SessionLocal() as session:
        session.query(ModerationHide).filter(
            ModerationHide.target_id == "r_test_seed"
        ).delete()
        session.query(UserSoftBan).filter(UserSoftBan.user_id == "user_demo").delete()
        session.query(Report).filter(Report.id == report_id).delete()
        session.commit()
