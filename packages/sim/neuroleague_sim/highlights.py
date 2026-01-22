from __future__ import annotations

from collections import defaultdict
from typing import Any

from neuroleague_sim.models import ReplayEvent, ReplayHighlight
from neuroleague_sim.modifiers import PORTALS


def _tagify(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("/", "_").replace(":", "_")


def _team_from_unit(uid: str) -> str | None:
    if uid.startswith("A"):
        return "A"
    if uid.startswith("B"):
        return "B"
    return None


def _unit_tags(uid: str, unit_meta: dict[str, dict[str, Any]]) -> list[str]:
    meta = unit_meta.get(uid, {})
    tags = [f"unit:{uid.lower()}"]
    creature_id = meta.get("creature_id")
    if creature_id:
        tags.append(f"creature:{_tagify(str(creature_id))}")
    for slot in ("weapon", "armor", "utility"):
        iid = (
            meta.get("items", {}).get(slot)
            if isinstance(meta.get("items"), dict)
            else None
        )
        if iid:
            tags.append(f"item:{_tagify(str(iid))}")
    return tags


def _non_overlapping(
    best: list[ReplayHighlight], candidate: ReplayHighlight, *, min_gap_ticks: int
) -> bool:
    for h in best:
        if not (
            candidate.end_t + min_gap_ticks < h.start_t
            or candidate.start_t > h.end_t + min_gap_ticks
        ):
            return False
    return True


def generate_highlights(
    events: list[ReplayEvent], *, unit_meta: dict[str, dict[str, Any]] | None = None
) -> list[ReplayHighlight]:
    unit_meta = unit_meta or {}
    max_t = max((e.t for e in events), default=0)
    min_gap = 15  # 0.75s at 20tps

    # Portal can tune highlight scoring to match a "set mechanic" feel.
    weights: dict[str, float] = {
        "synergy": 1.0,
        "revive": 1.0,
        "death": 1.0,
        "damage_spike": 1.0,
        "hp_swing": 1.0,
    }
    portal_id: str | None = None
    for e in events:
        if e.type == "PORTAL_SELECTED":
            portal_id = str(e.payload.get("portal_id") or "")
            break
    if portal_id and portal_id in PORTALS:
        hw = PORTALS[portal_id].rules_json.get("highlight_weights")
        if isinstance(hw, dict):
            for k, v in hw.items():
                try:
                    weights[str(k)] = float(v)
                except Exception:  # noqa: BLE001
                    pass

    candidates: list[tuple[int, ReplayHighlight]] = []

    for e in events:
        if e.type == "SYNERGY_TRIGGER":
            tag = str(e.payload.get("tag", "Synergy"))
            team = str(e.payload.get("team", "?"))
            count = int(e.payload.get("count", 0) or 0)
            threshold = int(e.payload.get("threshold", 0) or 0)
            bonus = int(e.payload.get("bonus", 0) or 0)
            bonus_breakdown = (
                e.payload.get("bonus_breakdown")
                if isinstance(e.payload, dict)
                else None
            )
            bonus_items: list[str] = []
            if isinstance(bonus_breakdown, dict):
                bonus_items = [
                    str(k) for k, v in bonus_breakdown.items() if int(v or 0) > 0
                ]
                bonus_items.sort()
            start_t = max(0, e.t)
            end_t = min(max_t, e.t + 20)
            tier_label = f"T{threshold}" if threshold else "T?"
            bonus_label = " (+Sigil)" if bonus > 0 else ""
            score = 520 + 80 * (threshold or 2) + 10 * min(6, count)
            score = int(score * float(weights.get("synergy", 1.0)))
            candidates.append(
                (
                    score,
                    ReplayHighlight(
                        rank=1,
                        start_t=start_t,
                        end_t=end_t,
                        title=f"{tag} {tier_label} Online{bonus_label}",
                        summary=(
                            f"Team {team} activates {tag} {tier_label} (x{count})."
                            + (f" Bonus +{bonus} via Sigil." if bonus > 0 else "")
                        ),
                        tags=[
                            "type:synergy",
                            f"team:{_tagify(team)}",
                            f"synergy:{_tagify(tag)}",
                            f"synergy_tier:{threshold or 0}",
                            *(f"item:{_tagify(iid)}" for iid in bonus_items),
                        ],
                    ),
                )
            )
        elif e.type == "AUGMENT_TRIGGER":
            trig_type = str(e.payload.get("type") or "")
            if trig_type != "revive":
                continue
            unit = str(e.payload.get("unit", "?"))
            team = str(e.payload.get("team", _team_from_unit(unit) or "?"))
            meta = unit_meta.get(unit, {})
            creature = meta.get("creature_name") or meta.get("creature_id") or "unit"
            start_t = max(0, e.t - 10)
            end_t = min(max_t, e.t + 20)
            score = int(880 * float(weights.get("revive", 1.0)))
            candidates.append(
                (
                    score,
                    ReplayHighlight(
                        rank=1,
                        start_t=start_t,
                        end_t=end_t,
                        title="Revive Online",
                        summary=f"{unit} ({creature}) revives — a clutch turning point.",
                        tags=[
                            "type:revive",
                            f"team:{_tagify(team)}",
                            *_unit_tags(unit, unit_meta),
                        ],
                    ),
                )
            )
        elif e.type == "DEATH":
            unit = str(e.payload.get("unit", "?"))
            team = _team_from_unit(unit) or "?"
            meta = unit_meta.get(unit, {})
            creature = meta.get("creature_name") or meta.get("creature_id") or "unit"
            start_t = max(0, e.t - 10)
            end_t = min(max_t, e.t + 10)
            score = int(800 * float(weights.get("death", 1.0)))
            candidates.append(
                (
                    score,
                    ReplayHighlight(
                        rank=1,
                        start_t=start_t,
                        end_t=end_t,
                        title="Unit Eliminated",
                        summary=f"{unit} ({creature}) is eliminated — the fight swings.",
                        tags=[
                            "type:death",
                            f"team:{team.lower()}",
                            *_unit_tags(unit, unit_meta),
                        ],
                    ),
                )
            )

    window = 40  # 2s
    dmg_by_window: dict[int, int] = defaultdict(int)
    dmg_by_window_team: dict[int, dict[str, int]] = defaultdict(
        lambda: {"A": 0, "B": 0}
    )
    dmg_by_window_source: dict[int, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for e in events:
        if e.type != "DAMAGE":
            continue
        w = e.t // window
        amount = int(e.payload.get("amount", 0) or 0)
        dmg_by_window[w] += amount
        src = str(e.payload.get("source", ""))
        dmg_by_window_source[w][src] += amount
        team = _team_from_unit(src)
        if team in ("A", "B"):
            dmg_by_window_team[w][team] += amount

    for w, dmg in sorted(dmg_by_window.items(), key=lambda kv: kv[1], reverse=True)[:6]:
        start_t = w * window
        end_t = min(max_t, start_t + window)
        dmg_a = dmg_by_window_team[w]["A"]
        dmg_b = dmg_by_window_team[w]["B"]
        lead = "A" if dmg_a > dmg_b else "B" if dmg_b > dmg_a else "draw"
        swing = abs(dmg_a - dmg_b)
        top_sources = sorted(
            dmg_by_window_source[w].items(), key=lambda kv: kv[1], reverse=True
        )[:2]
        source_tags: list[str] = []
        for src, _ in top_sources:
            source_tags.extend(_unit_tags(src, unit_meta))
        score = int(int(dmg) * float(weights.get("damage_spike", 1.0)))
        candidates.append(
            (
                score,
                ReplayHighlight(
                    rank=1,
                    start_t=start_t,
                    end_t=end_t,
                    title="Damage Spike",
                    summary=f"Massive burst ({dmg} total). Lead: {lead} (+{swing}).",
                    tags=[
                        "type:damage_spike",
                        f"lead:{lead.lower()}",
                        *sorted(set(source_tags)),
                    ],
                ),
            )
        )

    swing_by_window: dict[int, int] = {}
    for w, totals in dmg_by_window_team.items():
        swing_by_window[w] = abs(int(totals.get("A", 0)) - int(totals.get("B", 0)))

    for w, swing in sorted(swing_by_window.items(), key=lambda kv: kv[1], reverse=True)[
        :6
    ]:
        if swing <= 0:
            continue
        start_t = w * window
        end_t = min(max_t, start_t + window)
        dmg_a = dmg_by_window_team[w]["A"]
        dmg_b = dmg_by_window_team[w]["B"]
        lead = "A" if dmg_a > dmg_b else "B"
        top_sources = sorted(
            dmg_by_window_source[w].items(), key=lambda kv: kv[1], reverse=True
        )[:2]
        source_tags: list[str] = []
        for src, _ in top_sources:
            source_tags.extend(_unit_tags(src, unit_meta))
        base_score = 700 + swing
        score = int(int(base_score) * float(weights.get("hp_swing", 1.0)))
        candidates.append(
            (
                score,
                ReplayHighlight(
                    rank=1,
                    start_t=start_t,
                    end_t=end_t,
                    title="HP Swing",
                    summary=f"Team {lead} wins a key exchange (+{swing} net damage).",
                    tags=[
                        "type:hp_swing",
                        f"team:{lead.lower()}",
                        *sorted(set(source_tags)),
                    ],
                ),
            )
        )

    candidates = sorted(candidates, key=lambda kv: (-kv[0], kv[1].start_t))

    picked: list[ReplayHighlight] = []
    for _, c in candidates:
        if len(picked) >= 3:
            break
        if _non_overlapping(picked, c, min_gap_ticks=min_gap):
            picked.append(c)

    out: list[ReplayHighlight] = []
    for i, h in enumerate(picked, start=1):
        out.append(h.model_copy(update={"rank": i}))
    return out
