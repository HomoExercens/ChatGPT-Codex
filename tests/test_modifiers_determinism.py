from __future__ import annotations

from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.modifiers import (
    AUGMENT_ROUNDS,
    augment_offer,
    pick_portal_id,
    select_match_modifiers,
)
from neuroleague_sim.simulate import simulate_match


def test_match_id_portal_pick_is_stable() -> None:
    mid = "m_det_portal_001"
    assert pick_portal_id(mid) == pick_portal_id(mid)


def test_match_id_round_team_augment_offer_is_stable() -> None:
    mid = "m_det_offer_001"
    for r in AUGMENT_ROUNDS:
        a1 = augment_offer(mid, round_num=int(r), team="A")
        a2 = augment_offer(mid, round_num=int(r), team="A")
        b1 = augment_offer(mid, round_num=int(r), team="B")
        b2 = augment_offer(mid, round_num=int(r), team="B")
        assert a1 == a2
        assert b1 == b2
        assert len(a1) == len(set(a1)) == 3
        assert len(b1) == len(set(b1)) == 3


def test_replay_header_and_timeline_include_portal_and_augments() -> None:
    mid = "m_det_replay_mods_001"
    mods = select_match_modifiers(mid)

    assert isinstance(mods.get("portal_id"), str) and mods["portal_id"]
    for side_key in ("augments_a", "augments_b"):
        entries = mods.get(side_key) or []
        assert isinstance(entries, list) and len(entries) == len(AUGMENT_ROUNDS)
        for e in entries:
            assert isinstance(e, dict)
            assert int(e.get("round") or 0) in AUGMENT_ROUNDS
            options = e.get("options")
            assert isinstance(options, list) and len(options) == 3
            chosen = str(e.get("augment_id") or "")
            assert chosen and chosen in [str(x) for x in options]

    spec_a = BlueprintSpec(
        mode="1v1",
        team=[
            {
                "creature_id": "slime_knight",
                "formation": "front",
                "items": {"weapon": None, "armor": None, "utility": None},
            }
        ],
    )
    spec_b = BlueprintSpec(
        mode="1v1",
        team=[
            {
                "creature_id": "ember_fox",
                "formation": "front",
                "items": {"weapon": "ember_blade", "armor": None, "utility": None},
            }
        ],
    )
    replay = simulate_match(
        match_id=mid,
        seed_index=0,
        blueprint_a=spec_a,
        blueprint_b=spec_b,
        modifiers=mods,
    )

    assert replay.header.portal_id == mods["portal_id"]
    assert [a.augment_id for a in replay.header.augments_a] == [
        str(e.get("augment_id") or "") for e in mods["augments_a"]
    ]
    assert [a.augment_id for a in replay.header.augments_b] == [
        str(e.get("augment_id") or "") for e in mods["augments_b"]
    ]

    offers_a = [
        e
        for e in replay.timeline_events
        if e.type == "AUGMENT_OFFERED" and e.payload.get("team") == "A"
    ]
    assert offers_a
    for ev in offers_a:
        r = int(ev.payload.get("round") or 0)
        entry = next(
            (e for e in mods["augments_a"] if int(e.get("round") or 0) == r), None
        )
        assert entry is not None
        assert ev.payload.get("options") == entry.get("options")
