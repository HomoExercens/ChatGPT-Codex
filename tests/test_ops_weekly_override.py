from __future__ import annotations

import os


def _set_admin():
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    return {"X-Admin-Token": "admintest"}


def test_ops_weekly_override_roundtrip(api_client) -> None:
    headers = _set_admin()

    from neuroleague_sim.modifiers import AUGMENTS, PORTALS

    portal_ids = sorted(PORTALS.keys())[:2]
    assert portal_ids
    augment_ids = sorted(AUGMENTS.keys())[:3]

    wid = "2099W01"
    resp = api_client.post(
        "/api/ops/weekly/override",
        headers=headers,
        json={
            "week_id": wid,
            "name": "Test Weekly Override",
            "description": "override via ops endpoint",
            "featured_portal_ids": portal_ids,
            "featured_augment_ids": augment_ids,
            "tournament_rules": {"matches_counted": 10, "queue_open": True},
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["week_id"] == wid
    assert payload["override_active"] is True
    assert payload["theme"]["name"] == "Test Weekly Override"

    meta = api_client.get(f"/api/meta/weekly?week_id={wid}")
    assert meta.status_code == 200
    meta_payload = meta.json()
    assert meta_payload["week_id"] == wid
    assert [p["id"] for p in meta_payload.get("featured_portals") or []] == portal_ids

    cleared = api_client.post(
        "/api/ops/weekly/override",
        headers=headers,
        json={"clear": True, "week_id": wid},
    )
    assert cleared.status_code == 200

    after = api_client.get(f"/api/ops/weekly?week_id={wid}", headers=headers)
    assert after.status_code == 200
    after_payload = after.json()
    assert after_payload["override_active"] is False
