from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from neuroleague_sim.canonical import canonical_sha256
from neuroleague_sim.catalog import CREATURES, ITEMS, SYNERGY_EFFECTS, CreatureDef
from neuroleague_sim.modifiers import (
    AUGMENTS,
    PORTALS,
    augment_offer,
    select_match_modifiers,
)
from neuroleague_sim.models import (
    BlueprintSpec,
    Replay,
    ReplayAugmentChoice,
    ReplayEndSummary,
    ReplayEvent,
    ReplayHeader,
    ReplayUnit,
)
from neuroleague_sim.pack_loader import active_pack_hash
from neuroleague_sim.rng import derive_seed

RULESET_VERSION = "2026S1-v1"
TICKS_PER_SEC = 20
MAX_TICKS = 60 * TICKS_PER_SEC


@dataclass
class UnitState:
    uid: str
    team: Literal["A", "B"]
    creature: CreatureDef
    formation: Literal["front", "back"]
    equipped_items: tuple[str | None, str | None, str | None]  # weapon, armor, utility
    max_hp: int
    hp: int
    atk: int
    attack_interval_ticks: int
    crit_permille: int
    damage_reduction_permille: int
    next_attack_tick: int = 0
    next_heal_tick: int | None = None

    @property
    def alive(self) -> bool:
        return self.hp > 0


def _apply_permille(value: int, permille: int) -> int:
    return max(0, (value * (1000 + permille)) // 1000)


def _clamp_permille(x: int) -> int:
    return max(0, min(900, x))


def _init_team(team_id: Literal["A", "B"], spec: BlueprintSpec) -> list[UnitState]:
    units: list[UnitState] = []
    for idx, slot in enumerate(spec.team):
        creature = CREATURES[slot.creature_id]
        uid = f"{team_id}{idx + 1}"
        equipped_items = (slot.items.weapon, slot.items.armor, slot.items.utility)

        atk = creature.atk
        max_hp = creature.max_hp
        attack_interval_ticks = creature.attack_interval_ticks
        crit_permille = 50  # base 5%
        damage_reduction_permille = 0

        for slot_name in ("weapon", "armor", "utility"):
            item_id = getattr(slot.items, slot_name)
            if not item_id:
                continue
            item = ITEMS[item_id]
            atk = _apply_permille(atk, item.atk_permille)
            max_hp = _apply_permille(max_hp, item.hp_permille)
            crit_permille += item.crit_permille
            damage_reduction_permille += item.damage_reduction_permille
            if item.speed_permille:
                attack_interval_ticks = max(
                    1, (attack_interval_ticks * 1000) // (1000 + item.speed_permille)
                )

        crit_permille = _clamp_permille(crit_permille)
        damage_reduction_permille = _clamp_permille(damage_reduction_permille)

        unit = UnitState(
            uid=uid,
            team=team_id,
            creature=creature,
            formation=slot.formation,
            equipped_items=equipped_items,
            max_hp=max_hp,
            hp=max_hp,
            atk=atk,
            attack_interval_ticks=attack_interval_ticks,
            crit_permille=crit_permille,
            damage_reduction_permille=damage_reduction_permille,
        )
        if creature.heal_interval_ticks:
            unit.next_heal_tick = creature.heal_interval_ticks
        units.append(unit)
    return units


def _trigger_synergies(
    units: list[UnitState],
    events: list[ReplayEvent],
    *,
    extra_bonus_by_team: dict[str, dict[str, dict[str, int]]] | None = None,
) -> None:
    by_team: dict[str, list[UnitState]] = {"A": [], "B": []}
    for u in units:
        by_team[u.team].append(u)

    extra_bonus_by_team = extra_bonus_by_team or {}

    for team_id, team_units in by_team.items():
        base_counts: dict[str, int] = {}
        bonus_counts: dict[str, int] = {}
        bonus_breakdown_by_tag: dict[str, dict[str, int]] = {}
        for u in team_units:
            for tag in u.creature.tags:
                base_counts[tag] = base_counts.get(tag, 0) + 1
            for item_id in u.equipped_items:
                if not item_id:
                    continue
                item = ITEMS.get(item_id)
                if not item or not item.synergy_bonus:
                    continue
                for tag, bonus in item.synergy_bonus.items():
                    bonus = int(bonus)
                    if bonus <= 0:
                        continue
                    bonus_counts[tag] = bonus_counts.get(tag, 0) + bonus
                    bb = bonus_breakdown_by_tag.setdefault(tag, {})
                    bb[item_id] = bb.get(item_id, 0) + bonus

        # Match-level bonus sources (augments/portals/etc).
        extra_by_tag = extra_bonus_by_team.get(team_id, {})
        for tag, sources in (extra_by_tag or {}).items():
            if not isinstance(sources, dict):
                continue
            for source_id, bonus in sources.items():
                bonus = int(bonus or 0)
                if bonus <= 0:
                    continue
                bonus_counts[tag] = bonus_counts.get(tag, 0) + bonus
                bb = bonus_breakdown_by_tag.setdefault(tag, {})
                sid = str(source_id)
                bb[sid] = bb.get(sid, 0) + bonus

        for tag in sorted(base_counts.keys()):
            base_count = int(base_counts.get(tag, 0))
            if base_count < 2:
                continue
            bonus_total = int(bonus_counts.get(tag, 0))
            count = base_count + bonus_total
            effects_by_threshold = SYNERGY_EFFECTS.get(tag)
            if not effects_by_threshold:
                continue
            threshold = max(
                (t for t in effects_by_threshold.keys() if t <= count), default=None
            )
            if threshold is None:
                continue
            effect = effects_by_threshold[threshold]
            for u in team_units:
                if "atk_permille" in effect:
                    u.atk = _apply_permille(u.atk, effect["atk_permille"])
                if "hp_permille" in effect:
                    u.max_hp = _apply_permille(u.max_hp, effect["hp_permille"])
                    u.hp = _apply_permille(u.hp, effect["hp_permille"])
                if "crit_permille" in effect:
                    u.crit_permille = _clamp_permille(
                        u.crit_permille + effect["crit_permille"]
                    )
                if "damage_reduction_permille" in effect:
                    u.damage_reduction_permille = _clamp_permille(
                        u.damage_reduction_permille
                        + effect["damage_reduction_permille"]
                    )

            events.append(
                ReplayEvent(
                    t=0,
                    type="SYNERGY_TRIGGER",
                    payload={
                        "team": team_id,
                        "tag": tag,
                        "count": count,
                        "base_count": base_count,
                        "bonus": bonus_total,
                        "bonus_breakdown": bonus_breakdown_by_tag.get(tag, {}),
                        "threshold": threshold,
                        "effect": effect,
                    },
                )
            )


def _apply_team_mods(
    team_units: list[UnitState],
    *,
    atk_permille: int = 0,
    hp_permille: int = 0,
    crit_permille: int = 0,
    damage_reduction_permille: int = 0,
    speed_permille: int = 0,
) -> None:
    for u in team_units:
        if atk_permille:
            u.atk = _apply_permille(u.atk, int(atk_permille))
        if hp_permille:
            u.max_hp = _apply_permille(u.max_hp, int(hp_permille))
            u.hp = _apply_permille(u.hp, int(hp_permille))
        if crit_permille:
            u.crit_permille = _clamp_permille(u.crit_permille + int(crit_permille))
        if damage_reduction_permille:
            u.damage_reduction_permille = _clamp_permille(
                u.damage_reduction_permille + int(damage_reduction_permille)
            )
        if speed_permille:
            sp = int(speed_permille)
            denom = max(1, 1000 + sp)
            u.attack_interval_ticks = max(1, (u.attack_interval_ticks * 1000) // denom)


def _choose_target(
    attacker: UnitState, enemies: list[UnitState], rng: np.random.Generator
) -> UnitState | None:
    alive = [e for e in enemies if e.alive]
    if not alive:
        return None
    front = [e for e in alive if e.formation == "front"]
    pool = front if front else alive
    min_hp = min(e.hp for e in pool)
    candidates = [e for e in pool if e.hp == min_hp]
    if len(candidates) == 1:
        return candidates[0]
    return candidates[int(rng.integers(0, len(candidates)))]


def _pick_heal_target(
    team_units: list[UnitState], rng: np.random.Generator
) -> UnitState | None:
    alive = [u for u in team_units if u.alive and u.hp < u.max_hp]
    if not alive:
        return None
    min_score = min(u.hp * 1_000_000 // u.max_hp for u in alive)
    candidates = [u for u in alive if (u.hp * 1_000_000 // u.max_hp) == min_score]
    if len(candidates) == 1:
        return candidates[0]
    return candidates[int(rng.integers(0, len(candidates)))]


def simulate_match(
    *,
    match_id: str,
    seed_index: int,
    blueprint_a: BlueprintSpec,
    blueprint_b: BlueprintSpec,
    modifiers: dict[str, Any] | None = None,
) -> Replay:
    pack_hash = active_pack_hash()
    if (
        blueprint_a.ruleset_version != RULESET_VERSION
        or blueprint_b.ruleset_version != RULESET_VERSION
    ):
        raise ValueError("ruleset_version mismatch")
    if blueprint_a.mode != blueprint_b.mode:
        raise ValueError("mode mismatch")

    seed = derive_seed(match_id, seed_index)
    rng = np.random.default_rng(seed)

    events: list[ReplayEvent] = []
    team_a = _init_team("A", blueprint_a)
    team_b = _init_team("B", blueprint_b)
    units = [*team_a, *team_b]

    # Optional match modifiers (portals/augments). Keep default behavior unchanged unless provided.
    portal_id: str | None = None
    aug_a: list[dict[str, Any]] = []
    aug_b: list[dict[str, Any]] = []
    revive_available: dict[str, bool] = {"A": False, "B": False}
    extra_bonus_by_team: dict[str, dict[str, dict[str, int]]] = {"A": {}, "B": {}}

    if modifiers is not None:
        chosen = modifiers if isinstance(modifiers, dict) else {}
        portal_id = str(chosen.get("portal_id") or "")
        if portal_id not in PORTALS:
            chosen = select_match_modifiers(match_id)
            portal_id = str(chosen.get("portal_id") or "")

        aug_a = list(chosen.get("augments_a") or [])
        aug_b = list(chosen.get("augments_b") or [])

        portal = PORTALS.get(portal_id or "")
        portal_rules: dict[str, Any] = dict(portal.rules_json) if portal else {}

        events.append(
            ReplayEvent(
                t=0,
                type="PORTAL_SELECTED",
                payload={
                    "portal_id": portal_id,
                    "name": portal.name if portal else portal_id,
                },
            )
        )

        def _emit_team_augments(team_id: str, entries: list[dict[str, Any]]) -> None:
            for entry in entries:
                r = int(entry.get("round") or 0)
                aid = str(entry.get("augment_id") or "")
                adef = AUGMENTS.get(aid)
                if not adef:
                    continue
                options_raw = entry.get("options")
                if isinstance(options_raw, list):
                    options = [str(o) for o in options_raw if str(o)]
                else:
                    try:
                        options = augment_offer(match_id, round_num=r, team=team_id)  # type: ignore[arg-type]
                    except Exception:  # noqa: BLE001
                        options = []
                if options:
                    events.append(
                        ReplayEvent(
                            t=0,
                            type="AUGMENT_OFFERED",
                            payload={"team": team_id, "round": r, "options": options},
                        )
                    )
                events.append(
                    ReplayEvent(
                        t=0,
                        type="AUGMENT_CHOSEN",
                        payload={
                            "team": team_id,
                            "round": r,
                            "augment_id": adef.id,
                            "name": adef.name,
                            "tier": int(adef.tier),
                            "category": adef.category,
                        },
                    )
                )

        _emit_team_augments("A", aug_a)
        _emit_team_augments("B", aug_b)

        def _sum_permille(entries: list[dict[str, Any]], key: str) -> int:
            total = int(portal_rules.get(key) or 0)
            for entry in entries:
                aid = str(entry.get("augment_id") or "")
                adef = AUGMENTS.get(aid)
                if not adef:
                    continue
                total += int(adef.rules_json.get(key) or 0)
            return int(total)

        def _any_bool(entries: list[dict[str, Any]], key: str) -> bool:
            if bool(portal_rules.get(key)):
                return True
            for entry in entries:
                aid = str(entry.get("augment_id") or "")
                adef = AUGMENTS.get(aid)
                if not adef:
                    continue
                if bool(adef.rules_json.get(key)):
                    return True
            return False

        _apply_team_mods(
            team_a,
            atk_permille=_sum_permille(aug_a, "combat_atk_permille"),
            hp_permille=_sum_permille(aug_a, "combat_hp_permille"),
            crit_permille=_sum_permille(aug_a, "combat_crit_permille"),
            damage_reduction_permille=_sum_permille(
                aug_a, "combat_damage_reduction_permille"
            ),
            speed_permille=_sum_permille(aug_a, "combat_speed_permille"),
        )
        _apply_team_mods(
            team_b,
            atk_permille=_sum_permille(aug_b, "combat_atk_permille"),
            hp_permille=_sum_permille(aug_b, "combat_hp_permille"),
            crit_permille=_sum_permille(aug_b, "combat_crit_permille"),
            damage_reduction_permille=_sum_permille(
                aug_b, "combat_damage_reduction_permille"
            ),
            speed_permille=_sum_permille(aug_b, "combat_speed_permille"),
        )

        revive_available["A"] = _any_bool(aug_a, "combat_revive_once")
        revive_available["B"] = _any_bool(aug_b, "combat_revive_once")

        # Synergy bonus (Sigil-like) sources.
        def _add_synergy_source(team_id: str, source_id: str, bonus_map: Any) -> None:
            if not isinstance(bonus_map, dict):
                return
            for tag, bonus in bonus_map.items():
                bonus_i = int(bonus or 0)
                if bonus_i <= 0:
                    continue
                extra_bonus_by_team.setdefault(team_id, {}).setdefault(str(tag), {})
                extra_bonus_by_team[team_id][str(tag)][source_id] = (
                    extra_bonus_by_team[team_id][str(tag)].get(source_id, 0) + bonus_i
                )

        # Portal-wide accelerator: +N to all tags present (gated by base_count>=2 in _trigger_synergies).
        bonus_all = int(portal_rules.get("combat_synergy_bonus_all_online") or 0)
        if bonus_all > 0:
            tags_a = {t for u in team_a for t in u.creature.tags}
            tags_b = {t for u in team_b for t in u.creature.tags}
            for tag in tags_a:
                _add_synergy_source("A", f"portal:{portal_id}", {tag: bonus_all})
            for tag in tags_b:
                _add_synergy_source("B", f"portal:{portal_id}", {tag: bonus_all})

        _add_synergy_source(
            "A", f"portal:{portal_id}", portal_rules.get("synergy_bonus")
        )
        _add_synergy_source(
            "B", f"portal:{portal_id}", portal_rules.get("synergy_bonus")
        )

        for entry in aug_a:
            aid = str(entry.get("augment_id") or "")
            adef = AUGMENTS.get(aid)
            if adef:
                _add_synergy_source(
                    "A", f"augment:{adef.id}", adef.rules_json.get("synergy_bonus")
                )
        for entry in aug_b:
            aid = str(entry.get("augment_id") or "")
            adef = AUGMENTS.get(aid)
            if adef:
                _add_synergy_source(
                    "B", f"augment:{adef.id}", adef.rules_json.get("synergy_bonus")
                )

        _trigger_synergies(units, events, extra_bonus_by_team=extra_bonus_by_team)
    else:
        _trigger_synergies(units, events)

    for t in range(MAX_TICKS + 1):
        if not any(u.alive for u in team_a):
            winner: Literal["A", "B", "draw"] = "B"
            break
        if not any(u.alive for u in team_b):
            winner = "A"
            break

        for u in units:
            if not u.alive:
                continue
            if (
                u.creature.role == "Support"
                and u.next_heal_tick is not None
                and t >= u.next_heal_tick
            ):
                target = _pick_heal_target(team_a if u.team == "A" else team_b, rng)
                if target:
                    amount = max(1, u.atk // 3)
                    before = target.hp
                    target.hp = min(target.max_hp, target.hp + amount)
                    u.next_heal_tick = t + (u.creature.heal_interval_ticks or 40)
                    events.append(
                        ReplayEvent(
                            t=t,
                            type="HEAL",
                            payload={
                                "source": u.uid,
                                "target": target.uid,
                                "amount": target.hp - before,
                            },
                        )
                    )

            if t < u.next_attack_tick:
                continue
            target = _choose_target(u, team_b if u.team == "A" else team_a, rng)
            if not target:
                continue

            is_crit = int(rng.integers(0, 1000)) < u.crit_permille
            raw = u.atk * (2 if is_crit else 1)
            dmg = max(1, (raw * (1000 - target.damage_reduction_permille)) // 1000)
            before_hp = target.hp
            target.hp = max(0, target.hp - dmg)

            events.append(
                ReplayEvent(
                    t=t,
                    type="ATTACK",
                    payload={"source": u.uid, "target": target.uid, "crit": is_crit},
                )
            )
            events.append(
                ReplayEvent(
                    t=t,
                    type="DAMAGE",
                    payload={
                        "source": u.uid,
                        "target": target.uid,
                        "amount": before_hp - target.hp,
                    },
                )
            )

            if target.hp == 0:
                if revive_available.get(target.team, False):
                    revive_available[target.team] = False
                    target.hp = max(1, target.max_hp // 3)
                    events.append(
                        ReplayEvent(
                            t=t,
                            type="AUGMENT_TRIGGER",
                            payload={
                                "team": target.team,
                                "type": "revive",
                                "unit": target.uid,
                                "hp": int(target.hp),
                            },
                        )
                    )
                else:
                    events.append(
                        ReplayEvent(t=t, type="DEATH", payload={"unit": target.uid})
                    )

            u.next_attack_tick = t + u.attack_interval_ticks

    else:
        hp_a = sum(u.hp for u in team_a if u.alive)
        hp_b = sum(u.hp for u in team_b if u.alive)
        if hp_a > hp_b:
            winner = "A"
        elif hp_b > hp_a:
            winner = "B"
        else:
            winner = "draw"
        t = MAX_TICKS

    hp_a = sum(u.hp for u in team_a if u.alive)
    hp_b = sum(u.hp for u in team_b if u.alive)
    end = ReplayEndSummary(winner=winner, duration_ticks=t, hp_a=hp_a, hp_b=hp_b)
    events.append(ReplayEvent(t=t, type="END", payload=end.model_dump()))

    header = ReplayHeader(
        ruleset_version=RULESET_VERSION,
        pack_hash=pack_hash,
        match_id=match_id,
        seed_index=seed_index,
        seed=seed,
        mode=blueprint_a.mode,
        blueprint_a_hash=canonical_sha256(blueprint_a.model_dump()),
        blueprint_b_hash=canonical_sha256(blueprint_b.model_dump()),
        portal_id=portal_id,
        augments_a=[
            ReplayAugmentChoice(
                round=int(a.get("round") or 0),
                augment_id=str(a.get("augment_id") or ""),
            )
            for a in (aug_a or [])
            if str(a.get("augment_id") or "")
        ],
        augments_b=[
            ReplayAugmentChoice(
                round=int(a.get("round") or 0),
                augment_id=str(a.get("augment_id") or ""),
            )
            for a in (aug_b or [])
            if str(a.get("augment_id") or "")
        ],
        units=[
            *[
                ReplayUnit(
                    unit_id=u.uid,
                    team="A",
                    slot_index=i,
                    formation=u.formation,
                    creature_id=blueprint_a.team[i].creature_id,
                    creature_name=u.creature.name,
                    role=u.creature.role,
                    tags=list(u.creature.tags),
                    items=blueprint_a.team[i].items,
                    max_hp=u.max_hp,
                )
                for i, u in enumerate(team_a)
            ],
            *[
                ReplayUnit(
                    unit_id=u.uid,
                    team="B",
                    slot_index=i,
                    formation=u.formation,
                    creature_id=blueprint_b.team[i].creature_id,
                    creature_name=u.creature.name,
                    role=u.creature.role,
                    tags=list(u.creature.tags),
                    items=blueprint_b.team[i].items,
                    max_hp=u.max_hp,
                )
                for i, u in enumerate(team_b)
            ],
        ],
    )

    unit_meta: dict[str, dict[str, Any]] = {}
    for team_id, spec in (("A", blueprint_a), ("B", blueprint_b)):
        for idx, slot in enumerate(spec.team):
            uid = f"{team_id}{idx + 1}"
            creature = CREATURES[slot.creature_id]
            unit_meta[uid] = {
                "creature_id": slot.creature_id,
                "creature_name": creature.name,
                "role": creature.role,
                "tags": list(creature.tags),
                "items": {
                    "weapon": slot.items.weapon,
                    "armor": slot.items.armor,
                    "utility": slot.items.utility,
                },
            }

    from neuroleague_sim.highlights import generate_highlights

    highlights = generate_highlights(events, unit_meta=unit_meta)
    replay_obj: dict[str, Any] = {
        "header": header.model_dump(),
        "timeline_events": [e.model_dump() for e in events],
        "end_summary": end.model_dump(),
        "highlights": [h.model_dump() for h in highlights],
    }
    digest = canonical_sha256(replay_obj)

    replay = Replay(
        header=header,
        timeline_events=events,
        end_summary=end,
        highlights=highlights,
        digest=digest,
    )
    return replay
