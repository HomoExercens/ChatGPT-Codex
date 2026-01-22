from __future__ import annotations

import os


def _set_admin():
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    return {"X-Admin-Token": "admintest"}


def test_ops_packs_candidate_and_promote(api_client) -> None:
    headers = _set_admin()

    resp = api_client.get("/api/ops/packs", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert "active_ruleset_version" in payload
    assert isinstance(payload.get("available_packs"), list)

    cand = api_client.post(
        "/api/ops/packs/candidate",
        headers=headers,
        json={"path": "packs/default/v1/pack.json"},
    )
    assert cand.status_code == 200
    cand_payload = cand.json()
    assert cand_payload.get("candidate") is not None
    assert cand_payload["candidate"]["path"] == "packs/default/v1/pack.json"

    promoted = api_client.post(
        "/api/ops/packs/promote",
        headers=headers,
        json={"note": "test promote"},
    )
    assert promoted.status_code == 200
    promoted_payload = promoted.json()
    assert isinstance(promoted_payload.get("promotion"), dict)

    season = api_client.get("/api/meta/season")
    assert season.status_code == 200
    notes = season.json().get("patch_notes") or []
    assert any(
        str(n.get("title")) == "Pack promotion approved"
        for n in notes
        if isinstance(n, dict)
    )
