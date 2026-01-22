from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from neuroleague_sim.rng import derive_seed


TeamId = Literal["A", "B"]


@dataclass(frozen=True)
class PortalDef:
    id: str
    name: str
    description: str
    rules_json: dict[str, Any]
    rarity: int = 1
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AugmentDef:
    id: str
    name: str
    description: str
    tier: int  # 1..3
    category: str  # econ/synergy/combat/reroll/level/viral
    rules_json: dict[str, Any]
    tags: tuple[str, ...] = ()


# NOTE: IDs must be stable and deterministically ordered (sorted keys are used for sampling).
PORTALS: dict[str, PortalDef] = {
    "portal_shop_plus1": PortalDef(
        id="portal_shop_plus1",
        name="Expanded Lab Shop",
        description="Draft shop feels bigger. In battle: slight damage pressure for faster rounds.",
        rules_json={
            "draft_shop_creature_slots_delta": 1,
            "draft_shop_item_slots_delta": 1,
            "combat_atk_permille": 50,
        },
        tags=("econ",),
    ),
    "portal_income_plus2": PortalDef(
        id="portal_income_plus2",
        name="Grant Funding",
        description="Draft income is higher. In battle: sturdier frontline.",
        rules_json={"draft_income_delta": 2, "combat_hp_permille": 60},
        tags=("econ",),
    ),
    "portal_free_reroll": PortalDef(
        id="portal_free_reroll",
        name="Free Reroll Protocol",
        description="First reroll each round is free. In battle: crit chance is slightly higher.",
        rules_json={"draft_free_reroll_per_round": 1, "combat_crit_permille": 40},
        tags=("reroll",),
    ),
    "portal_fast_leveling": PortalDef(
        id="portal_fast_leveling",
        name="Accelerated Research",
        description="Level-ups are cheaper. In battle: attack speed is slightly higher.",
        rules_json={
            "draft_levelup_cost_delta": -2,
            "draft_levelup_cost_min": 1,
            "combat_speed_permille": 60,
        },
        tags=("level",),
    ),
    "portal_sigils_richer": PortalDef(
        id="portal_sigils_richer",
        name="Sigil Overflow",
        description="Sigils appear more often. In battle: synergy is easier to activate.",
        rules_json={"draft_sigil_bias": 1, "combat_synergy_bonus_all_online": 1},
        tags=("synergy",),
    ),
    "portal_short_rounds": PortalDef(
        id="portal_short_rounds",
        name="Compressed Schedule",
        description="Draft has fewer rounds. In battle: stronger opening burst.",
        rules_json={"draft_rounds": 5, "combat_atk_permille": 80},
        tags=("viral",),
    ),
    "portal_high_variance": PortalDef(
        id="portal_high_variance",
        name="High Variance Lab",
        description="Rarer offers appear. In battle: higher highs and lower lows (crit up, defense down).",
        rules_json={
            "draft_rarity_bias": {"r3_bonus": 0.1},
            "combat_crit_permille": 80,
            "combat_damage_reduction_permille": -40,
        },
        rarity=2,
        tags=("high_variance",),
    ),
    "portal_story_mode": PortalDef(
        id="portal_story_mode",
        name="Story Mode",
        description="Spectator-first. Highlights favor synergy swings and clutch moments.",
        rules_json={
            "highlight_weights": {
                "synergy": 1.35,
                "revive": 1.25,
                "death": 0.95,
                "damage_spike": 1.05,
                "hp_swing": 1.05,
            }
        },
        tags=("viral",),
    ),
}


# 30 augments across 3 tiers (10 per tier). Keep effects conservative.
AUGMENTS: dict[str, AugmentDef] = {
    # Tier 1 (mild)
    "aug_t1_microshield": AugmentDef(
        id="aug_t1_microshield",
        name="Micro-Shield",
        description="Start combat with a small HP buffer.",
        tier=1,
        category="combat",
        rules_json={"combat_hp_permille": 50},
    ),
    "aug_t1_sharp_edges": AugmentDef(
        id="aug_t1_sharp_edges",
        name="Sharp Edges",
        description="Slightly higher damage output.",
        tier=1,
        category="combat",
        rules_json={"combat_atk_permille": 50},
    ),
    "aug_t1_targeting_patch": AugmentDef(
        id="aug_t1_targeting_patch",
        name="Targeting Patch",
        description="Slightly higher crit chance.",
        tier=1,
        category="combat",
        rules_json={"combat_crit_permille": 40},
    ),
    "aug_t1_quick_servos": AugmentDef(
        id="aug_t1_quick_servos",
        name="Quick Servos",
        description="Slightly faster attacks.",
        tier=1,
        category="combat",
        rules_json={"combat_speed_permille": 60},
    ),
    "aug_t1_plating": AugmentDef(
        id="aug_t1_plating",
        name="Light Plating",
        description="Slightly more damage reduction.",
        tier=1,
        category="combat",
        rules_json={"combat_damage_reduction_permille": 40},
    ),
    "aug_t1_knight_emblem": AugmentDef(
        id="aug_t1_knight_emblem",
        name="Knight Emblem",
        description="Knight synergy count +1 once online (base 2+).",
        tier=1,
        category="synergy",
        rules_json={"synergy_bonus": {"Knight": 1}},
        tags=("synergy:knight",),
    ),
    "aug_t1_mech_emblem": AugmentDef(
        id="aug_t1_mech_emblem",
        name="Mech Emblem",
        description="Mech synergy count +1 once online (base 2+).",
        tier=1,
        category="synergy",
        rules_json={"synergy_bonus": {"Mech": 1}},
        tags=("synergy:mech",),
    ),
    "aug_t1_mystic_emblem": AugmentDef(
        id="aug_t1_mystic_emblem",
        name="Mystic Emblem",
        description="Mystic synergy count +1 once online (base 2+).",
        tier=1,
        category="synergy",
        rules_json={"synergy_bonus": {"Mystic": 1}},
        tags=("synergy:mystic",),
    ),
    "aug_t1_beast_emblem": AugmentDef(
        id="aug_t1_beast_emblem",
        name="Beast Emblem",
        description="Beast synergy count +1 once online (base 2+).",
        tier=1,
        category="synergy",
        rules_json={"synergy_bonus": {"Beast": 1}},
        tags=("synergy:beast",),
    ),
    "aug_t1_fire_emblem": AugmentDef(
        id="aug_t1_fire_emblem",
        name="Fire Emblem",
        description="Fire synergy count +1 once online (base 2+).",
        tier=1,
        category="synergy",
        rules_json={"synergy_bonus": {"Fire": 1}},
        tags=("synergy:fire",),
    ),
    # Tier 2 (medium)
    "aug_t2_heavy_shields": AugmentDef(
        id="aug_t2_heavy_shields",
        name="Heavy Shields",
        description="More HP for the whole team.",
        tier=2,
        category="combat",
        rules_json={"combat_hp_permille": 120},
    ),
    "aug_t2_overclock": AugmentDef(
        id="aug_t2_overclock",
        name="Overclock",
        description="More attack speed for the whole team.",
        tier=2,
        category="combat",
        rules_json={"combat_speed_permille": 140},
    ),
    "aug_t2_precision": AugmentDef(
        id="aug_t2_precision",
        name="Precision",
        description="More crit chance for the whole team.",
        tier=2,
        category="combat",
        rules_json={"combat_crit_permille": 90},
    ),
    "aug_t2_brutality": AugmentDef(
        id="aug_t2_brutality",
        name="Brutality",
        description="More damage for the whole team.",
        tier=2,
        category="combat",
        rules_json={"combat_atk_permille": 120},
    ),
    "aug_t2_armor_matrix": AugmentDef(
        id="aug_t2_armor_matrix",
        name="Armor Matrix",
        description="More damage reduction for the whole team.",
        tier=2,
        category="combat",
        rules_json={"combat_damage_reduction_permille": 90},
    ),
    "aug_t2_clutch_revive": AugmentDef(
        id="aug_t2_clutch_revive",
        name="Clutch Revive",
        description="First would-be death revives once per match.",
        tier=2,
        category="combat",
        rules_json={"combat_revive_once": True},
        tags=("revive",),
    ),
    "aug_t2_void_emblem": AugmentDef(
        id="aug_t2_void_emblem",
        name="Void Emblem",
        description="Void synergy count +1 once online (base 2+).",
        tier=2,
        category="synergy",
        rules_json={"synergy_bonus": {"Void": 1}},
        tags=("synergy:void",),
    ),
    "aug_t2_vine_emblem": AugmentDef(
        id="aug_t2_vine_emblem",
        name="Vine Emblem",
        description="Vine synergy count +1 once online (base 2+).",
        tier=2,
        category="synergy",
        rules_json={"synergy_bonus": {"Vine": 1}},
        tags=("synergy:vine",),
    ),
    "aug_t2_medic_emblem": AugmentDef(
        id="aug_t2_medic_emblem",
        name="Medic Emblem",
        description="Medic synergy count +1 once online (base 2+).",
        tier=2,
        category="synergy",
        rules_json={"synergy_bonus": {"Medic": 1}},
        tags=("synergy:medic",),
    ),
    "aug_t2_storm_emblem": AugmentDef(
        id="aug_t2_storm_emblem",
        name="Storm Emblem",
        description="Storm synergy count +1 once online (base 2+).",
        tier=2,
        category="synergy",
        rules_json={"synergy_bonus": {"Storm": 1}},
        tags=("synergy:storm",),
    ),
    # Tier 3 (strong, still safe)
    "aug_t3_last_stand": AugmentDef(
        id="aug_t3_last_stand",
        name="Last Stand",
        description="Big HP + defense boost.",
        tier=3,
        category="combat",
        rules_json={"combat_hp_permille": 180, "combat_damage_reduction_permille": 120},
    ),
    "aug_t3_glass_cannon": AugmentDef(
        id="aug_t3_glass_cannon",
        name="Glass Cannon",
        description="Big damage + crit, but slightly lower defense.",
        tier=3,
        category="combat",
        rules_json={
            "combat_atk_permille": 180,
            "combat_crit_permille": 140,
            "combat_damage_reduction_permille": -60,
        },
    ),
    "aug_t3_rapid_fire": AugmentDef(
        id="aug_t3_rapid_fire",
        name="Rapid Fire",
        description="Very fast attacks.",
        tier=3,
        category="combat",
        rules_json={"combat_speed_permille": 240},
    ),
    "aug_t3_iron_wall": AugmentDef(
        id="aug_t3_iron_wall",
        name="Iron Wall",
        description="Very high damage reduction.",
        tier=3,
        category="combat",
        rules_json={"combat_damage_reduction_permille": 220},
    ),
    "aug_t3_double_down": AugmentDef(
        id="aug_t3_double_down",
        name="Double Down",
        description="High damage + speed.",
        tier=3,
        category="combat",
        rules_json={"combat_atk_permille": 140, "combat_speed_permille": 180},
    ),
    "aug_t3_phoenix_protocol": AugmentDef(
        id="aug_t3_phoenix_protocol",
        name="Phoenix Protocol",
        description="Revive once per match and gain some crit chance.",
        tier=3,
        category="combat",
        rules_json={"combat_revive_once": True, "combat_crit_permille": 80},
        tags=("revive",),
    ),
    "aug_t3_arcane_emblem": AugmentDef(
        id="aug_t3_arcane_emblem",
        name="Arcane Emblem",
        description="Mystic synergy count +2 once online (base 2+).",
        tier=3,
        category="synergy",
        rules_json={"synergy_bonus": {"Mystic": 2}},
        tags=("synergy:mystic",),
    ),
    "aug_t3_guardian_emblem": AugmentDef(
        id="aug_t3_guardian_emblem",
        name="Guardian Emblem",
        description="Knight synergy count +2 once online (base 2+).",
        tier=3,
        category="synergy",
        rules_json={"synergy_bonus": {"Knight": 2}},
        tags=("synergy:knight",),
    ),
    "aug_t3_inferno_emblem": AugmentDef(
        id="aug_t3_inferno_emblem",
        name="Inferno Emblem",
        description="Fire synergy count +2 once online (base 2+).",
        tier=3,
        category="synergy",
        rules_json={"synergy_bonus": {"Fire": 2}},
        tags=("synergy:fire",),
    ),
    "aug_t3_void_emblem_plus": AugmentDef(
        id="aug_t3_void_emblem_plus",
        name="Void Emblem+",
        description="Void synergy count +2 once online (base 2+).",
        tier=3,
        category="synergy",
        rules_json={"synergy_bonus": {"Void": 2}},
        tags=("synergy:void",),
    ),
}


AUGMENT_ROUNDS: tuple[int, ...] = (2, 4, 6)


def _default_portal_ids() -> list[str]:
    return sorted(PORTALS.keys())


def _default_augment_ids_by_tier() -> dict[int, list[str]]:
    by_tier: dict[int, list[str]] = {}
    for aid, adef in AUGMENTS.items():
        by_tier.setdefault(int(adef.tier), []).append(str(aid))
    for tier, ids in by_tier.items():
        ids.sort()
    return by_tier


def pick_portal_id(match_id: str, *, portal_ids: list[str] | None = None) -> str:
    ids = sorted(set(portal_ids)) if portal_ids else _default_portal_ids()
    if not ids:
        raise RuntimeError("No portals defined")
    seed = derive_seed(match_id, "portal")
    idx = int(seed) % len(ids)
    return ids[idx]


def _tier_for_round(round_num: int) -> int:
    if int(round_num) <= 2:
        return 1
    if int(round_num) <= 4:
        return 2
    return 3


def augment_offer(
    match_id: str,
    *,
    round_num: int,
    team: TeamId,
    augment_ids_by_tier: dict[int, list[str]] | None = None,
) -> list[str]:
    tier = _tier_for_round(round_num)
    tier_map = augment_ids_by_tier or _default_augment_ids_by_tier()
    pool = list(tier_map.get(tier, []))
    if not pool:
        return []
    seed = derive_seed(match_id, f"augment_offer_{round_num}_{team}")
    rng = np.random.default_rng(seed)
    picked: list[str] = []
    for _ in range(min(3, len(pool))):
        idx = int(rng.integers(0, len(pool)))
        picked.append(pool.pop(idx))
    return picked


def augment_choose(
    match_id: str,
    *,
    round_num: int,
    team: TeamId,
    augment_ids_by_tier: dict[int, list[str]] | None = None,
) -> str:
    options = augment_offer(
        match_id,
        round_num=round_num,
        team=team,
        augment_ids_by_tier=augment_ids_by_tier,
    )
    if not options:
        raise RuntimeError("No augment options available")
    seed = derive_seed(match_id, f"augment_pick_{round_num}_{team}")
    idx = int(seed) % len(options)
    return options[idx]


def select_match_modifiers(
    match_id: str,
    *,
    portal_ids: list[str] | None = None,
    augment_ids_by_tier: dict[int, list[str]] | None = None,
) -> dict[str, Any]:
    portal_id = pick_portal_id(match_id, portal_ids=portal_ids)
    augments_a: list[dict[str, Any]] = []
    augments_b: list[dict[str, Any]] = []
    for team, out in (("A", augments_a), ("B", augments_b)):
        for r in AUGMENT_ROUNDS:
            options = augment_offer(
                match_id,
                round_num=int(r),
                team=team,
                augment_ids_by_tier=augment_ids_by_tier,  # type: ignore[arg-type]
            )
            if not options:
                raise RuntimeError("No augment options available")
            seed = derive_seed(match_id, f"augment_pick_{int(r)}_{team}")
            chosen = str(options[int(seed) % len(options)])
            out.append({"round": int(r), "augment_id": chosen, "options": options})
    return {"portal_id": portal_id, "augments_a": augments_a, "augments_b": augments_b}


def portal_public() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid in sorted(PORTALS.keys()):
        p = PORTALS[pid]
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "rarity": int(p.rarity),
                "tags": list(p.tags),
            }
        )
    return out


def augments_public() -> list[dict[str, Any]]:
    ids = sorted(AUGMENTS.keys())
    out: list[dict[str, Any]] = []
    for aid in ids:
        a = AUGMENTS[aid]
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "tier": int(a.tier),
                "category": a.category,
                "tags": list(a.tags),
            }
        )
    return out
