from __future__ import annotations

import os


def _set_admin():
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    return {"X-Admin-Token": "admintest"}


def test_ops_metrics_endpoints_shape(api_client) -> None:
    headers = _set_admin()

    r1 = api_client.get("/api/ops/metrics/summary?range=7d", headers=headers)
    assert r1.status_code == 200
    j1 = r1.json()
    assert "kpis" in j1
    assert isinstance(j1.get("daily"), list)

    r2 = api_client.get(
        "/api/ops/metrics/funnel?range=7d&funnel=growth_v1", headers=headers
    )
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("funnel") == "growth_v1"
    assert isinstance(j2.get("steps"), list)

    r2b = api_client.get(
        "/api/ops/metrics/funnel_daily?range=7d&funnel=share_v1", headers=headers
    )
    assert r2b.status_code == 200
    j2b = r2b.json()
    assert j2b.get("funnel") == "share_v1"
    assert isinstance(j2b.get("steps"), list)

    r2c = api_client.get(
        "/api/ops/metrics/funnel_daily?range=7d&funnel=clips_v1", headers=headers
    )
    assert r2c.status_code == 200
    j2c = r2c.json()
    assert j2c.get("funnel") == "clips_v1"
    assert isinstance(j2c.get("steps"), list)

    r3 = api_client.get("/api/ops/metrics/experiments?range=7d", headers=headers)
    assert r3.status_code == 200
    j3 = r3.json()
    assert isinstance(j3.get("experiments"), list)

    r3b = api_client.get(
        "/api/ops/metrics/experiments/hero_feed_v1_summary?range=7d", headers=headers
    )
    assert r3b.status_code == 200
    j3b = r3b.json()
    assert j3b.get("experiment_key") == "hero_feed_v1"
    assert isinstance(j3b.get("variants"), dict)
    assert isinstance(j3b.get("guardrails"), dict)

    r3c = api_client.get(
        "/api/ops/metrics/experiments/gesture_thresholds_v1_summary?range=7d&segment=all",
        headers=headers,
    )
    assert r3c.status_code == 200
    j3c = r3c.json()
    assert j3c.get("experiment_key") == "gesture_thresholds_v1"
    assert j3c.get("segment") == "all"
    assert isinstance(j3c.get("variants"), dict)
    assert isinstance(j3c.get("guardrails"), dict)
    for vid, v in (j3c.get("variants") or {}).items():
        assert isinstance(v, dict)
        cov = v.get("coverage")
        assert isinstance(cov, dict)
        assert "uach_available_rate" in cov
        assert "container_hint_coverage" in cov
        assert "unknown_segment_rate" in cov
        cfg = v.get("thresholds_config")
        assert isinstance(cfg, dict)
        if vid in {"control", "variant_a", "variant_b"}:
            assert "double_tap_ms" in cfg

    r4 = api_client.post("/api/ops/metrics/rollup?range=7d", headers=headers)
    assert r4.status_code == 200
    j4 = r4.json()
    assert j4.get("ok") is True

    r5 = api_client.get(
        "/api/ops/metrics/shorts_variants?range=7d", headers=headers
    )
    assert r5.status_code == 200
    j5 = r5.json()
    assert isinstance(j5.get("tables"), list)
    assert isinstance(j5.get("available_channels"), list)
    assert isinstance(j5.get("groups"), list)
    assert isinstance(j5.get("filters"), dict)
