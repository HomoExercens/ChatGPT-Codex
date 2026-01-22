from __future__ import annotations

import os


def _set_admin():
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    return {"X-Admin-Token": "admintest"}


def test_request_id_header_present_on_success_and_error(api_client) -> None:
    ok = api_client.get("/api/health")
    assert ok.status_code == 200
    assert ok.headers.get("X-Request-Id")

    unauthorized = api_client.get("/api/ops/status")
    assert unauthorized.status_code == 401
    assert unauthorized.headers.get("X-Request-Id")


def test_http_metrics_include_latency_histogram(api_client) -> None:
    api_client.get("/api/health")
    metrics = api_client.get("/api/metrics")
    assert metrics.status_code == 200
    assert "neuroleague_http_request_duration_seconds_bucket" in metrics.text


def test_ops_recent_errors_endpoint_includes_recent_error(api_client) -> None:
    api_client.get("/api/ops/status")  # 401 (no token)
    headers = _set_admin()
    resp = api_client.get(
        "/api/ops/metrics/errors_recent?minutes=60&limit=50", headers=headers
    )
    assert resp.status_code == 200
    j = resp.json()
    assert "items" in j and isinstance(j["items"], list)
    assert any(
        it.get("path") == "/api/ops/status" and int(it.get("status") or 0) == 401
        for it in j["items"]
    )

