from __future__ import annotations

from pathlib import Path

from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.pack_loader import active_pack_hash, compute_pack_hash, load_pack
from neuroleague_sim.simulate import simulate_match


def test_pack_hash_matches_pack_json() -> None:
    path = (
        Path(__file__).resolve().parents[1] / "packs" / "default" / "v1" / "pack.json"
    )
    pack = load_pack(path)
    assert isinstance(pack.get("pack_hash"), str) and pack["pack_hash"]
    assert pack["pack_hash"] == compute_pack_hash(pack)

    ah = active_pack_hash()
    assert isinstance(ah, str) and ah
    assert ah == pack["pack_hash"]


def test_replay_header_includes_pack_hash() -> None:
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
        match_id="m_pack_test", seed_index=0, blueprint_a=spec_a, blueprint_b=spec_b
    )
    assert replay.header.pack_hash == active_pack_hash()
