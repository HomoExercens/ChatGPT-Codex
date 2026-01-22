from __future__ import annotations

from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.simulate import simulate_match


def test_sim_determinism_digest_stable_100x() -> None:
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

    digests = {
        simulate_match(
            match_id="m_det", seed_index=0, blueprint_a=spec_a, blueprint_b=spec_b
        ).digest
        for _ in range(100)
    }
    assert len(digests) == 1
