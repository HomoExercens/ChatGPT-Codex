from __future__ import annotations


def _payload(*, portal_id: str = "", augment_id: str = "", synergy: str = "") -> dict:
    tags: list[str] = ["type:hp_swing"]
    if synergy:
        tags.append(f"synergy:{synergy}")
        tags.append("type:synergy")
    header = {
        "match_id": "m_test",
        "mode": "1v1",
    }
    if portal_id:
        header["portal_id"] = portal_id
    if augment_id:
        header["augments_a"] = [{"augment_id": augment_id}]
    return {
        "header": header,
        "end_summary": {"duration_ticks": 200, "winner": "A", "hp_a": 10},
        "highlights": [
            {
                "start_t": 0,
                "end_t": 100,
                "title": "Turning Point",
                "summary": "Big swing",
                "tags": tags,
            }
        ],
        "timeline_events": [],
    }


def test_captions_v2_hook_prefers_portal() -> None:
    from neuroleague_api.clip_render import captions_plan_for_segment

    plan = captions_plan_for_segment(
        replay_payload=_payload(
            portal_id="portal_storm",
            augment_id="augment_revive",
            synergy="stormline",
        ),
        start_tick=0,
        end_tick=40,
        template_id="A",
    )
    assert plan.template_id == "A"
    assert plan.lines[0].startswith("PORTAL ")
    assert "STORM" in plan.lines[0]


def test_captions_v2_hook_uses_augment_when_no_portal() -> None:
    from neuroleague_api.clip_render import captions_plan_for_segment

    plan = captions_plan_for_segment(
        replay_payload=_payload(augment_id="augment_revive"),
        start_tick=0,
        end_tick=40,
        template_id="B",
    )
    assert plan.template_id == "B"
    assert plan.lines[0].startswith("AUGMENT ")
    assert "REVIVE" in plan.lines[0]


def test_captions_v2_hook_uses_synergy_when_available() -> None:
    from neuroleague_api.clip_render import captions_plan_for_segment

    plan = captions_plan_for_segment(
        replay_payload=_payload(synergy="stormline"),
        start_tick=0,
        end_tick=40,
        template_id="C",
    )
    assert plan.template_id == "C"
    assert plan.lines[0].startswith("SYNERGY ")
    assert "STORMLINE" in plan.lines[0]


def test_captions_v2_hook_timing_gate() -> None:
    from neuroleague_api.clip_render import TICKS_PER_SEC, captions_lines_for_frame

    start_tick = 100
    lines = ["PORTAL STORM", "BEAT THIS"]
    assert (
        captions_lines_for_frame(
            captions_lines=lines,
            captions_template_id="A",
            frame_tick=start_tick,
            segment_start_tick=start_tick,
        )
        == ["PORTAL STORM"]
    )
    assert (
        captions_lines_for_frame(
            captions_lines=lines,
            captions_template_id="A",
            frame_tick=start_tick + int(0.75 * TICKS_PER_SEC),
            segment_start_tick=start_tick,
        )
        == ["PORTAL STORM"]
    )
    assert captions_lines_for_frame(
        captions_lines=lines,
        captions_template_id="A",
        frame_tick=start_tick + int(0.8 * TICKS_PER_SEC),
        segment_start_tick=start_tick,
    ) == lines

