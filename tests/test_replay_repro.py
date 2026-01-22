from __future__ import annotations

from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.simulate import simulate_match


def test_replay_repro_same_end_summary_and_digest() -> None:
    spec_a = BlueprintSpec(
        mode="1v1",
        team=[
            {
                "creature_id": "clockwork_golem",
                "formation": "front",
                "items": {
                    "weapon": "plasma_lance",
                    "armor": "reinforced_plate",
                    "utility": "targeting_array",
                },
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

    replay_a = simulate_match(
        match_id="m_repro", seed_index=1, blueprint_a=spec_a, blueprint_b=spec_b
    )
    replay_b = simulate_match(
        match_id=replay_a.header.match_id,
        seed_index=replay_a.header.seed_index,
        blueprint_a=spec_a,
        blueprint_b=spec_b,
    )
    assert replay_b.end_summary == replay_a.end_summary
    assert replay_b.digest == replay_a.digest
