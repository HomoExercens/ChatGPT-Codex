from __future__ import annotations

from neuroleague_sim.models import BlueprintSpec, ReplayEvent
from neuroleague_sim.simulate import simulate_match


def _find_synergy_event(
    events: list[ReplayEvent], *, team: str, tag: str
) -> ReplayEvent:
    for e in events:
        if e.type != "SYNERGY_TRIGGER":
            continue
        if str(e.payload.get("team")) != team:
            continue
        if str(e.payload.get("tag")) != tag:
            continue
        return e
    raise AssertionError(f"missing SYNERGY_TRIGGER for team={team} tag={tag}")


def test_synergy_bonus_counts_team_t4_and_t6() -> None:
    # Mech base count is 3 (Mech/Heavy + Mech/Knight + Scrap/Mech).
    base_team = [
        {
            "creature_id": "clockwork_golem",
            "formation": "front",
            "items": {"utility": None},
        },
        {
            "creature_id": "iron_striker",
            "formation": "front",
            "items": {"utility": None},
        },
        {
            "creature_id": "scrap_artificer",
            "formation": "back",
            "items": {"utility": None},
        },
    ]

    spec_t4 = BlueprintSpec(
        mode="team",
        team=[
            {**base_team[0], "items": {"utility": "mech_sigil"}},
            base_team[1],
            base_team[2],
        ],
    )
    spec_t6 = BlueprintSpec(
        mode="team",
        team=[
            {**base_team[0], "items": {"utility": "mech_sigil"}},
            {**base_team[1], "items": {"utility": "mech_sigil"}},
            {**base_team[2], "items": {"utility": "mech_sigil"}},
        ],
    )

    enemy = BlueprintSpec(
        mode="team",
        team=[
            {
                "creature_id": "thornback_boar",
                "formation": "front",
                "items": {"utility": None},
            },
            {
                "creature_id": "ember_fox",
                "formation": "front",
                "items": {"utility": None},
            },
            {
                "creature_id": "field_medic",
                "formation": "back",
                "items": {"utility": None},
            },
        ],
    )

    r4 = simulate_match(
        match_id="test_synergy_bonus_t4",
        seed_index=0,
        blueprint_a=spec_t4,
        blueprint_b=enemy,
    )
    e4 = _find_synergy_event(r4.timeline_events, team="A", tag="Mech")
    assert int(e4.payload.get("base_count", 0)) == 3
    assert int(e4.payload.get("bonus", 0)) == 1
    assert int(e4.payload.get("count", 0)) == 4
    assert int(e4.payload.get("threshold", 0)) == 4
    assert isinstance(e4.payload.get("bonus_breakdown"), dict)
    assert int(e4.payload["bonus_breakdown"].get("mech_sigil", 0)) == 1

    r6 = simulate_match(
        match_id="test_synergy_bonus_t6",
        seed_index=0,
        blueprint_a=spec_t6,
        blueprint_b=enemy,
    )
    e6 = _find_synergy_event(r6.timeline_events, team="A", tag="Mech")
    assert int(e6.payload.get("base_count", 0)) == 3
    assert int(e6.payload.get("bonus", 0)) == 3
    assert int(e6.payload.get("count", 0)) == 6
    assert int(e6.payload.get("threshold", 0)) == 6
    assert isinstance(e6.payload.get("bonus_breakdown"), dict)
    assert int(e6.payload["bonus_breakdown"].get("mech_sigil", 0)) == 3
