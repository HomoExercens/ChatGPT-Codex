from __future__ import annotations


def test_blueprint_import_fork_lineage_and_gallery(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bps = api_client.get("/api/blueprints", headers=headers)
    assert bps.status_code == 200
    demo_bp = next(bp for bp in bps.json() if bp["id"] == "bp_demo_1v1")
    build_code = demo_bp.get("build_code")
    assert isinstance(build_code, str) and build_code.startswith("NL1_")

    imported = api_client.post(
        "/api/blueprints/import", headers=headers, json={"build_code": build_code}
    )
    assert imported.status_code == 200
    imported_payload = imported.json()
    assert imported_payload["status"] == "draft"
    assert imported_payload.get("build_code")

    forked = api_client.post(
        "/api/blueprints/bp_bot_1v1/fork", headers=headers, json={}
    )
    assert forked.status_code == 200
    forked_payload = forked.json()
    assert forked_payload.get("forked_from_id") == "bp_bot_1v1"

    lineage = api_client.get(
        f"/api/blueprints/{forked_payload['id']}/lineage", headers=headers
    )
    assert lineage.status_code == 200
    chain = lineage.json().get("chain") or []
    assert len(chain) >= 2
    assert chain[0]["blueprint_id"] == forked_payload["id"]
    assert chain[1]["blueprint_id"] == "bp_bot_1v1"

    gallery = api_client.get(
        "/api/gallery/blueprints?mode=1v1&limit=20", headers=headers
    )
    assert gallery.status_code == 200
    items = gallery.json()
    assert any(
        (row.get("creator") or {}).get("user_id") == "user_demo" for row in items
    )

    bod = api_client.get("/api/gallery/build_of_day?mode=1v1", headers=headers)
    assert bod.status_code == 200
    assert bod.json().get("mode") == "1v1"
