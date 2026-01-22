from __future__ import annotations


def test_best_clip_endpoint_uses_top_highlight(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from neuroleague_api.clip_render import (
        CAPTIONS_VERSION,
        best_clip_segment,
        cache_key,
        captions_plan_for_segment,
    )
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Replay
    from neuroleague_api.storage import load_replay_json

    with SessionLocal() as session:
        replay = session.get(Replay, "r_test_seed")
        assert replay is not None
        payload = load_replay_json(artifact_path=replay.artifact_path)
        expected_start, expected_end = best_clip_segment(payload, max_duration_sec=12.0)
        captions_plan = captions_plan_for_segment(
            replay_payload=payload, start_tick=expected_start, end_tick=expected_end
        )
        digest = str(replay.digest or "")
        assert digest
        vertical_key = cache_key(
            replay_digest=digest,
            kind="clip_mp4",
            start_tick=expected_start,
            end_tick=expected_end,
            fps=12,
            scale=1,
            theme="dark",
            aspect="9:16",
            captions_version=captions_plan.version or CAPTIONS_VERSION,
            captions_template_id=captions_plan.template_id,
        )
        assert vertical_key

    resp = api_client.get("/api/matches/m_test_seed/best_clip", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["match_id"] == "m_test_seed"
    assert data["replay_id"] == "r_test_seed"
    assert int(data["start_tick"]) == expected_start
    assert int(data["end_tick"]) == expected_end
    assert "v=1" in str(data.get("share_url_vertical") or "")
    assets = data.get("assets") or []
    assert any(
        a.get("kind") == "vertical_mp4" and a.get("cache_key") == vertical_key
        for a in assets
    )


def test_best_clip_segment_fallback_when_no_highlights() -> None:
    from neuroleague_api.clip_render import best_clip_segment

    payload = {
        "highlights": [],
        "end_summary": {"duration_ticks": 400},  # 20s
    }
    start_tick, end_tick = best_clip_segment(payload, max_duration_sec=12.0)
    assert (start_tick, end_tick) == (100, 300)


def test_best_clip_segment_expands_short_highlight_to_min_duration() -> None:
    from neuroleague_api.clip_render import best_clip_segment

    payload = {
        "header": {"match_id": "m_x", "portal_id": "portal_clockwork"},
        "highlights": [{"start_t": 0, "end_t": 40, "title": "HP Swing"}],  # 2s
        "end_summary": {"duration_ticks": 400},  # 20s
    }
    start_tick, end_tick = best_clip_segment(payload, max_duration_sec=12.0)
    # min duration is 6s => 120 ticks; segment anchored around highlight.
    assert (start_tick, end_tick) == (0, 120)


def test_captions_plan_deterministic_and_versioned() -> None:
    from neuroleague_api.clip_render import CAPTIONS_VERSION, captions_plan_for_segment

    payload = {
        "header": {"match_id": "m_tpl_001", "portal_id": "portal_clockwork"},
        "highlights": [
            {
                "start_t": 0,
                "end_t": 120,
                "title": "HP Swing",
                "summary": "Team B wins a key exchange (+821 net damage).",
                "tags": ["type:hp_swing", "team:b"],
            }
        ],
        "end_summary": {"duration_ticks": 400, "winner": "B", "hp_b": 1},
    }
    a = captions_plan_for_segment(replay_payload=payload, start_tick=0, end_tick=120)
    b = captions_plan_for_segment(replay_payload=payload, start_tick=0, end_tick=120)
    assert a.version == CAPTIONS_VERSION
    assert a == b
    assert a.template_id
    assert a.lines and len(a.lines) <= 3


def test_captions_plan_forced_template_id_overrides_event_type() -> None:
    from neuroleague_api.clip_render import captions_plan_for_segment

    payload = {
        "header": {"match_id": "m_tpl_force_001", "portal_id": "portal_clockwork"},
        "highlights": [
            {
                "start_t": 0,
                "end_t": 120,
                "title": "HP Swing",
                "summary": "Team B wins a key exchange (+821 net damage).",
                "tags": ["type:hp_swing", "team:b"],
            }
        ],
        "end_summary": {"duration_ticks": 400, "winner": "B", "hp_b": 1},
    }
    plan = captions_plan_for_segment(
        replay_payload=payload,
        replay_id="r_tpl_force_001",
        start_tick=0,
        end_tick=120,
        template_id="A",
    )
    assert plan.template_id == "A"
    assert plan.lines[:2] == ["BEAT THIS", "HP Swing"]
