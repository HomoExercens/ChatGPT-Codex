from __future__ import annotations


def test_build_code_decode_and_import_endpoints(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bps = api_client.get("/api/blueprints", headers=headers)
    assert bps.status_code == 200
    demo_bp = next(bp for bp in bps.json() if bp["id"] == "bp_demo_1v1")
    code = demo_bp.get("build_code")
    assert isinstance(code, str) and code.startswith("NL1_")

    decoded = api_client.post(
        "/api/build_code/decode", headers=headers, json={"code": code}
    )
    assert decoded.status_code == 200
    decoded_payload = decoded.json()
    assert decoded_payload.get("ok") is True
    assert decoded_payload.get("mode") == "1v1"
    assert isinstance(decoded_payload.get("warnings"), list)
    spec = decoded_payload.get("blueprint_spec")
    assert isinstance(spec, dict) and spec.get("mode") == "1v1"

    imported = api_client.post(
        "/api/build_code/import",
        headers=headers,
        json={"code": code, "name": "Imported via build code"},
    )
    assert imported.status_code == 200
    imported_payload = imported.json()
    assert imported_payload.get("ok") is True

    bp = imported_payload.get("blueprint") or {}
    assert bp.get("status") == "draft"
    assert str(bp.get("forked_from_id") or "") == "bp_demo_1v1"
    imported_id = str(bp.get("id") or "")
    assert imported_id.startswith("bp_")

    lineage = api_client.get(f"/api/blueprints/{imported_id}/lineage", headers=headers)
    assert lineage.status_code == 200
    chain = lineage.json().get("chain") or []
    assert len(chain) >= 2
    assert chain[0]["blueprint_id"] == imported_id
    assert chain[1]["blueprint_id"] == "bp_demo_1v1"
    assert chain[0].get("origin_code_hash")
