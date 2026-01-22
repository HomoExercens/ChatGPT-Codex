from __future__ import annotations

import os


def _set_admin():
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    return {"X-Admin-Token": "admintest"}


def test_ops_status_shape(api_client) -> None:
    headers = _set_admin()
    resp = api_client.get("/api/ops/status", headers=headers)
    assert resp.status_code == 200
    j = resp.json()
    assert "ruleset_version" in j
    assert "db" in j and isinstance(j["db"], dict)
    assert "storage" in j and isinstance(j["storage"], dict)
    assert "ray" in j and isinstance(j["ray"], dict)
    assert "render_jobs" in j and isinstance(j["render_jobs"], dict)
