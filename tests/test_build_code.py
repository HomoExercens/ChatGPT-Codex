from __future__ import annotations

import pytest

from neuroleague_api.build_code import decode_build_code, encode_build_code
from neuroleague_sim.models import BlueprintSpec


def test_build_code_round_trip_stable() -> None:
    spec = BlueprintSpec(
        mode="team",
        team=[
            {
                "creature_id": "clockwork_golem",
                "formation": "front",
                "items": {
                    "weapon": "plasma_lance",
                    "armor": "reinforced_plate",
                    "utility": "targeting_array",
                },
            },
            {
                "creature_id": "iron_striker",
                "formation": "front",
                "items": {"weapon": "ion_repeater", "armor": None, "utility": None},
            },
            {
                "creature_id": "crystal_weaver",
                "formation": "back",
                "items": {"weapon": None, "armor": None, "utility": "healing_drones"},
            },
        ],
    )

    code1 = encode_build_code(spec=spec)
    code2 = encode_build_code(spec=spec)
    assert code1 == code2
    assert code1.startswith("NL1_")

    decoded = decode_build_code(build_code=code1)
    assert decoded.model_dump() == spec.model_dump()


def test_build_code_rejects_invalid_prefix() -> None:
    with pytest.raises(ValueError):
        decode_build_code(build_code="BAD_xxx")
