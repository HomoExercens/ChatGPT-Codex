from __future__ import annotations


def test_ops_build_of_day_override(api_client, monkeypatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_ADMIN_TOKEN", "admintest")

    headers = {"X-Admin-Token": "admintest"}
    resp = api_client.get("/api/ops/build_of_day?mode=1v1&days=1", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    today = str(payload.get("today") or "")
    assert today

    ov = api_client.post(
        "/api/ops/build_of_day/override",
        headers=headers,
        json={"mode": "1v1", "date": today, "blueprint_id": "bp_demo_1v1"},
    )
    assert ov.status_code == 200
    ov_payload = ov.json()
    entries = ov_payload.get("entries") or []
    assert entries and entries[0].get("date") == today
    assert entries[0].get("picked_blueprint_id") == "bp_demo_1v1"
    assert entries[0].get("source") == "override"

    # Cleanup: avoid leaking overrides across tests.
    from neuroleague_api.build_of_day import BOD_OVERRIDE_KEY
    from neuroleague_api.storage_backend import get_storage_backend

    backend = get_storage_backend()
    backend.delete(key=BOD_OVERRIDE_KEY)
