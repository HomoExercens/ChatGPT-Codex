from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest


def test_wow_score_deterministic() -> None:
    from neuroleague_api.hero_clips import DEFAULT_WOW_WEIGHTS, compute_wow_score

    now = datetime(2026, 1, 24, 12, 0, 0, tzinfo=UTC)
    created_at = datetime(2026, 1, 23, 12, 0, 0, tzinfo=UTC)
    engagement = {
        "views": 120.0,
        "completions": 54.0,
        "share_open": 8.0,
        "clip_share": 3.0,
        "beat_this_click": 7.0,
        "reply_clip_shared": 2.0,
        "reactions": 11.0,
    }
    features = {
        "highlight_count": 4.0,
        "damage_spikes": 2.0,
        "badge_perfect": 1.0,
        "badge_one_shot": 0.0,
        "badge_clutch": 0.0,
    }

    s1 = compute_wow_score(
        now=now,
        created_at=created_at,
        engagement=engagement,
        features=features,
        half_life_days=5.0,
        weights=DEFAULT_WOW_WEIGHTS,
    )
    s2 = compute_wow_score(
        now=now,
        created_at=created_at,
        engagement=engagement,
        features=features,
        half_life_days=5.0,
        weights=DEFAULT_WOW_WEIGHTS,
    )
    assert s1 == pytest.approx(s2, rel=0, abs=0)
    assert s1 > 0.0


def test_ops_hero_clips_recompute_requires_admin(api_client) -> None:
    os.environ.pop("NEUROLEAGUE_ADMIN_TOKEN", None)
    r = api_client.post("/api/ops/hero_clips/recompute")
    assert r.status_code == 401


def test_ops_hero_clips_recompute_writes_ops_files(api_client) -> None:
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    r = api_client.post("/api/ops/hero_clips/recompute", headers={"X-Admin-Token": "admintest"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert "by_mode" in j

    from neuroleague_api.core.config import Settings

    settings = Settings()
    root = Path(settings.artifacts_dir)
    assert (root / "ops" / "hero_clips.override.json").exists()
    assert (root / "ops" / "hero_clips.auto.json").exists()
    assert (root / "ops" / "hero_clips.json").exists()


def test_ops_hero_clips_candidates_requires_admin(api_client) -> None:
    os.environ.pop("NEUROLEAGUE_ADMIN_TOKEN", None)
    r = api_client.get("/api/ops/hero_clips/candidates?range=14d")
    assert r.status_code == 401


def test_ops_hero_clips_candidates_shape_and_override_update(api_client) -> None:
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"

    r0 = api_client.post("/api/ops/hero_clips/recompute", headers={"X-Admin-Token": "admintest"})
    assert r0.status_code == 200

    r1 = api_client.get("/api/ops/hero_clips/candidates?range=14d", headers={"X-Admin-Token": "admintest"})
    assert r1.status_code == 200
    j1 = r1.json()
    assert isinstance(j1.get("by_mode"), dict)
    assert "1v1" in j1["by_mode"]
    assert isinstance(j1["by_mode"]["1v1"].get("items"), list)
    assert isinstance(j1["by_mode"]["1v1"].get("pinned"), list)
    assert isinstance(j1["by_mode"]["1v1"].get("excluded"), list)

    r2 = api_client.post(
        "/api/ops/hero_clips/override",
        headers={"X-Admin-Token": "admintest"},
        json={"mode": "1v1", "op": "pin", "replay_id": "r_test_seed"},
    )
    assert r2.status_code == 200

    r3 = api_client.get("/api/ops/hero_clips/candidates?range=14d", headers={"X-Admin-Token": "admintest"})
    assert r3.status_code == 200
    j3 = r3.json()
    assert "r_test_seed" in (j3.get("by_mode", {}).get("1v1", {}).get("pinned") or [])
