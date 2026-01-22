from __future__ import annotations

import os

import orjson

from neuroleague_api.storage_backend import get_storage_backend


def _set_admin():
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    return {"X-Admin-Token": "admintest"}


def test_ops_preflight_latest_shape(api_client) -> None:
    headers = _set_admin()

    backend = get_storage_backend()
    backend.put_bytes(
        key="ops/preflight_latest.json",
        data=orjson.dumps(
            {
                "generated_at": "2026-01-18T00:00:00Z",
                "ruleset_version": "2026S1-v1",
                "baseline_pack_hash": "b" * 64,
                "candidate_pack_hash": "c" * 64,
                "modes": [],
            },
            option=orjson.OPT_SORT_KEYS,
        ),
        content_type="application/json",
    )
    backend.put_bytes(
        key="ops/preflight_latest.md",
        data=b"# Preflight\n",
        content_type="text/markdown",
    )

    resp = api_client.get("/api/ops/preflight/latest", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("available") in (True, False)
    assert isinstance(payload.get("report"), dict)
    report = payload["report"]
    assert "ruleset_version" in report
    assert "modes" in report
    assert payload.get("artifact_url")
