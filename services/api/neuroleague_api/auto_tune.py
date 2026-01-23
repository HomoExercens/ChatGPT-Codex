from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Literal

from neuroleague_sim.canonical import canonical_sha256
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.simulate import MAX_TICKS, simulate_match

AutoTunePreset = Literal["dps", "tank", "speed"]


@dataclass(frozen=True)
class AutoTuneCandidate:
    spec: BlueprintSpec
    label: str


def _baseline_opponents(mode: Literal["1v1", "team"]) -> list[BlueprintSpec]:
    if mode == "1v1":
        return [
            BlueprintSpec(
                ruleset_version="2026S1-v1",
                mode="1v1",
                team=[
                    {
                        "creature_id": "slime_knight",
                        "formation": "front",
                        "items": {"weapon": "thorn_spear", "armor": "medic_vest", "utility": "targeting_array"},
                    }
                ],
            )
        ]
    return [
        BlueprintSpec(
            ruleset_version="2026S1-v1",
            mode="team",
            team=[
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {"weapon": None, "armor": "reinforced_plate", "utility": "smoke_emitter"},
                },
                {
                    "creature_id": "iron_striker",
                    "formation": "front",
                    "items": {"weapon": "plasma_lance", "armor": "thorn_mail", "utility": "targeting_array"},
                },
                {
                    "creature_id": "crystal_weaver",
                    "formation": "back",
                    "items": {"weapon": "crystal_staff", "armor": "nanofiber_cloak", "utility": "healing_drones"},
                },
            ],
        )
    ]


def _preset_item_pool(preset: AutoTunePreset) -> dict[str, list[str | None]]:
    if preset == "dps":
        return {
            "weapon": ["void_dagger", "ember_blade", "plasma_lance", "crystal_staff", "thorn_spear"],
            "armor": [None, "medic_vest", "nanofiber_cloak"],
            "utility": ["targeting_array", "adrenaline_module", "clockwork_core"],
        }
    if preset == "tank":
        return {
            "weapon": ["plasma_lance", "thorn_spear", "ion_repeater"],
            "armor": ["runic_barrier", "reinforced_plate", "coolant_shell", "thorn_mail", "medic_vest"],
            "utility": ["smoke_emitter", "phoenix_ash", "healing_drones"],
        }
    return {
        "weapon": ["ion_repeater", "thorn_spear", "plasma_lance"],
        "armor": ["nanofiber_cloak", "coolant_shell", "medic_vest"],
        "utility": ["adrenaline_module", "clockwork_core", "targeting_array"],
    }


def _relevant_slots(preset: AutoTunePreset) -> list[str]:
    if preset == "tank":
        return ["armor", "utility"]
    return ["weapon", "utility"]


def _hash_u32(s: str) -> int:
    d = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(d[:4], "little", signed=False)


def _make_candidates(spec: BlueprintSpec, preset: AutoTunePreset) -> list[AutoTuneCandidate]:
    pool = _preset_item_pool(preset)
    slots = _relevant_slots(preset)
    out: list[AutoTuneCandidate] = [AutoTuneCandidate(spec=spec, label="base")]

    # Full preset candidate (apply top item in each relevant slot for every unit).
    full = spec.model_copy(deep=True)
    for u in full.team:
        for slot in slots:
            items = u.items.model_copy(deep=True)
            setattr(items, slot, pool[slot][0])
            u.items = items
    out.append(AutoTuneCandidate(spec=full, label="preset_all"))

    # Single-slot candidates (swap one slot on one unit).
    for unit_idx in range(len(spec.team)):
        for slot in slots:
            for item_id in pool[slot]:
                cand = spec.model_copy(deep=True)
                items = cand.team[unit_idx].items.model_copy(deep=True)
                setattr(items, slot, item_id)
                cand.team[unit_idx].items = items
                out.append(
                    AutoTuneCandidate(
                        spec=cand, label=f"u{unit_idx}:{slot}={item_id or 'none'}"
                    )
                )

    # Deterministic order: sort by spec hash + label.
    out.sort(key=lambda c: (canonical_sha256(c.spec.model_dump()), c.label))
    return out


def _score_replay(preset: AutoTunePreset, *, winner: str, hp_a: int, hp_b: int, duration: int) -> int:
    win = 1 if winner == "A" else 0
    draw = 1 if winner == "draw" else 0
    hp_delta = int(hp_a) - int(hp_b)

    score = win * 1_000_000 + draw * 250_000 + hp_delta * 100
    if preset == "tank":
        score += int(hp_a) * 20
    if preset == "speed":
        score += int(MAX_TICKS - min(MAX_TICKS, max(0, duration))) * 50
    return score


def auto_tune(
    *,
    blueprint_id: str,
    spec: BlueprintSpec,
    preset: AutoTunePreset,
    seed_count: int = 3,
) -> tuple[BlueprintSpec, dict[str, Any]]:
    opponents = _baseline_opponents(spec.mode)
    candidates = _make_candidates(spec, preset)

    best_score: int | None = None
    best: AutoTuneCandidate | None = None
    best_wins = 0
    best_draws = 0
    best_losses = 0

    for cand_idx, cand in enumerate(candidates):
        score = 0
        wins = 0
        draws = 0
        losses = 0
        for opp_idx, opp in enumerate(opponents):
            for seed_index in range(int(seed_count)):
                match_id = f"autotune:{blueprint_id}:{preset}:{cand_idx}:{opp_idx}:{_hash_u32(cand.label)}"
                replay = simulate_match(
                    match_id=match_id,
                    seed_index=seed_index,
                    blueprint_a=cand.spec,
                    blueprint_b=opp,
                    modifiers=None,
                )
                w = replay.end_summary.winner
                if w == "A":
                    wins += 1
                elif w == "draw":
                    draws += 1
                else:
                    losses += 1
                score += _score_replay(
                    preset,
                    winner=w,
                    hp_a=int(replay.end_summary.hp_a),
                    hp_b=int(replay.end_summary.hp_b),
                    duration=int(replay.end_summary.duration_ticks),
                )
        if best_score is None or score > best_score:
            best_score = score
            best = cand
            best_wins, best_draws, best_losses = wins, draws, losses

    if best is None:
        best = candidates[0]
        best_score = 0

    # Diff summary (items only)
    changes: list[dict[str, Any]] = []
    for i in range(len(spec.team)):
        before = spec.team[i].items
        after = best.spec.team[i].items
        for slot in ("weapon", "armor", "utility"):
            b = getattr(before, slot)
            a = getattr(after, slot)
            if b != a:
                changes.append(
                    {
                        "slot_index": i,
                        "creature_id": best.spec.team[i].creature_id,
                        "item_slot": slot,
                        "from": b,
                        "to": a,
                    }
                )

    meta = {
        "preset": preset,
        "seed_count": int(seed_count),
        "opponents": len(opponents),
        "candidates_tested": len(candidates),
        "best_label": best.label,
        "best_score": int(best_score or 0),
        "wins": int(best_wins),
        "draws": int(best_draws),
        "losses": int(best_losses),
        "changes": changes,
    }
    return best.spec, meta

