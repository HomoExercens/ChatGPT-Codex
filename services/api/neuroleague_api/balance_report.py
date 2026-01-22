from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
from typing import Any, Literal

import orjson
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.models import Blueprint, Match


def _result_score_a(result: str) -> float:
    if result == "A":
        return 1.0
    if result == "B":
        return 0.0
    return 0.5


def _result_label(result: str) -> Literal["win", "loss", "draw"]:
    if result == "A":
        return "win"
    if result == "B":
        return "loss"
    return "draw"


def _ensure_row(
    table: dict[str, dict[str, Any]],
    *,
    rid: str,
    name: str | None = None,
) -> dict[str, Any]:
    row = table.get(rid)
    if row is not None:
        return row
    row = {
        "id": rid,
        "name": name or rid,
        "uses": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "winrate": 0.0,
        "pick_rate": 0.0,
        "avg_elo_delta": 0.0,
        "_elo_sum": 0,
    }
    table[rid] = row
    return row


def _add_outcome(row: dict[str, Any], *, result: str, elo_delta_a: int) -> None:
    row["uses"] += 1
    out = _result_label(result)
    if out == "win":
        row["wins"] += 1
    elif out == "loss":
        row["losses"] += 1
    else:
        row["draws"] += 1
    row["_elo_sum"] += int(elo_delta_a or 0)


def _finalize_rows(
    rows: dict[str, dict[str, Any]],
    *,
    total_matches: int,
    low_confidence_min_samples: int,
) -> list[dict[str, Any]]:
    out = list(rows.values())
    for r in out:
        uses = int(r["uses"] or 0)
        r["winrate"] = (int(r["wins"]) + 0.5 * int(r["draws"])) / uses if uses else 0.0
        r["pick_rate"] = uses / total_matches if total_matches else 0.0
        r["avg_elo_delta"] = (int(r["_elo_sum"]) / uses) if uses else 0.0
        r["low_confidence"] = uses < int(low_confidence_min_samples)
        r.pop("_elo_sum", None)
    return out


def _synergy_counts_with_bonus(
    spec: dict[str, Any],
) -> tuple[dict[str, int], dict[str, int]]:
    from neuroleague_sim.catalog import CREATURES, ITEMS

    team = spec.get("team") or []
    base_counts: dict[str, int] = {}
    bonus_counts: dict[str, int] = {}
    for slot in team:
        if not isinstance(slot, dict):
            continue
        cid = str(slot.get("creature_id") or "")
        if cid and cid in CREATURES:
            for tag in CREATURES[cid].tags:
                base_counts[tag] = base_counts.get(tag, 0) + 1
        items = slot.get("items") or {}
        if not isinstance(items, dict):
            continue
        for slot_name in ("weapon", "armor", "utility"):
            iid = items.get(slot_name)
            if not iid:
                continue
            idef = ITEMS.get(str(iid))
            if not idef or not getattr(idef, "synergy_bonus", None):
                continue
            for tag, bonus in dict(idef.synergy_bonus).items():
                bonus = int(bonus)
                if bonus <= 0:
                    continue
                bonus_counts[tag] = bonus_counts.get(tag, 0) + bonus

    # Sigil-style bonus is only meaningful once a synergy is already online (>=2).
    for tag, base in list(base_counts.items()):
        if int(base) < 2:
            bonus_counts.pop(tag, None)

    return base_counts, bonus_counts


def _synergy_threshold(count: int) -> int:
    if count >= 6:
        return 6
    if count >= 4:
        return 4
    if count >= 2:
        return 2
    return 0


def compute_balance_report(
    db: Session,
    *,
    ruleset_version: str,
    queue_type: str = "ranked",
    generated_at: str | None = None,
    limit_matches: int = 10_000,
    low_confidence_min_samples: int = 50,
) -> dict[str, Any]:
    from neuroleague_sim.catalog import ITEMS
    from neuroleague_sim.modifiers import AUGMENTS, PORTALS

    gen = generated_at or datetime.now(UTC).isoformat()

    modes: dict[str, Any] = {}
    for mode in ("1v1", "team"):
        q = (
            select(Match)
            .where(Match.status == "done")
            .where(Match.ruleset_version == ruleset_version)
            .where(Match.mode == mode)
            .where(Match.queue_type == queue_type)
            .order_by(Match.created_at.desc())
            .limit(int(limit_matches))
        )
        matches = db.scalars(q).all()

        total = len(matches)
        wins = sum(1 for m in matches if m.result == "A")
        losses = sum(1 for m in matches if m.result == "B")
        draws = sum(1 for m in matches if m.result == "draw")
        overall_wr = (wins + 0.5 * draws) / total if total else 0.0
        avg_elo_delta = (
            (sum(int(m.elo_delta_a or 0) for m in matches) / total) if total else 0.0
        )

        portal_rows: dict[str, dict[str, Any]] = {}
        augment_rows: dict[str, dict[str, Any]] = {}
        creature_rows: dict[str, dict[str, Any]] = {}
        item_rows: dict[str, dict[str, Any]] = {}
        sigil_rows: dict[str, dict[str, Any]] = {}
        synergy_rows: dict[str, dict[str, Any]] = {}
        synergy_pair_rows: dict[str, dict[str, Any]] = {}

        bp_ids = sorted({str(m.blueprint_a_id) for m in matches if m.blueprint_a_id})
        bp_specs: dict[str, dict[str, Any]] = {}
        if bp_ids:
            for bp in db.scalars(
                select(Blueprint).where(Blueprint.id.in_(bp_ids))
            ).all():
                try:
                    bp_specs[bp.id] = orjson.loads(bp.spec_json)
                except Exception:  # noqa: BLE001
                    continue

        for m in matches:
            pid = str(getattr(m, "portal_id", None) or "legacy")
            prow = _ensure_row(
                portal_rows,
                rid=pid,
                name=(PORTALS.get(pid).name if pid in PORTALS else pid),
            )
            _add_outcome(prow, result=m.result, elo_delta_a=int(m.elo_delta_a or 0))

            # Augments picked for A-side (queueing player).
            try:
                aug_a = orjson.loads(getattr(m, "augments_a_json", "[]") or "[]")
            except Exception:  # noqa: BLE001
                aug_a = []
            if isinstance(aug_a, list):
                for entry in aug_a:
                    if not isinstance(entry, dict):
                        continue
                    aid = str(entry.get("augment_id") or "")
                    if not aid:
                        continue
                    adef = AUGMENTS.get(aid)
                    arow = _ensure_row(
                        augment_rows,
                        rid=aid,
                        name=(adef.name if adef else aid),
                    )
                    arow["tier"] = int(adef.tier) if adef else None
                    arow["category"] = adef.category if adef else None
                    _add_outcome(
                        arow, result=m.result, elo_delta_a=int(m.elo_delta_a or 0)
                    )

            if not m.blueprint_a_id:
                continue
            spec = bp_specs.get(str(m.blueprint_a_id))
            if not spec:
                continue

            team = spec.get("team") or []
            creatures_in_match: set[str] = set()
            items_in_match: set[str] = set()
            sigils_in_match: set[str] = set()

            for slot in team:
                if not isinstance(slot, dict):
                    continue
                cid = str(slot.get("creature_id") or "")
                if cid:
                    creatures_in_match.add(cid)
                items = slot.get("items") or {}
                if not isinstance(items, dict):
                    continue
                for slot_name in ("weapon", "armor", "utility"):
                    iid = items.get(slot_name)
                    if not iid:
                        continue
                    sid = str(iid)
                    items_in_match.add(sid)
                    idef = ITEMS.get(sid)
                    if idef and getattr(idef, "synergy_bonus", None):
                        sigils_in_match.add(sid)

            for cid in sorted(creatures_in_match):
                crow = _ensure_row(creature_rows, rid=cid, name=cid)
                _add_outcome(crow, result=m.result, elo_delta_a=int(m.elo_delta_a or 0))

            for iid in sorted(items_in_match):
                irow = _ensure_row(item_rows, rid=iid, name=iid)
                idef = ITEMS.get(iid)
                irow["rarity"] = int(getattr(idef, "rarity", 1) or 1) if idef else 1
                irow["slot"] = str(getattr(idef, "slot", "") or "") if idef else ""
                _add_outcome(irow, result=m.result, elo_delta_a=int(m.elo_delta_a or 0))

            for sid in sorted(sigils_in_match):
                srow = _ensure_row(sigil_rows, rid=sid, name=sid)
                idef = ITEMS.get(sid)
                srow["rarity"] = int(getattr(idef, "rarity", 1) or 1) if idef else 1
                srow["slot"] = str(getattr(idef, "slot", "") or "") if idef else ""
                srow["synergy_bonus"] = (
                    dict(getattr(idef, "synergy_bonus", {}) or {}) if idef else {}
                )
                _add_outcome(srow, result=m.result, elo_delta_a=int(m.elo_delta_a or 0))

            # Synergy stats (with Sigil bonus applied only if base>=2).
            base_counts, bonus_counts = _synergy_counts_with_bonus(spec)
            active: list[str] = []
            for tag in sorted(base_counts.keys()):
                base = int(base_counts.get(tag, 0))
                bonus = int(bonus_counts.get(tag, 0))
                total_count = base + bonus
                threshold = _synergy_threshold(total_count)
                if threshold < 2:
                    continue
                srow = _ensure_row(synergy_rows, rid=tag, name=tag)
                srow.setdefault("tier_counts", {"2": 0, "4": 0, "6": 0})
                tkey = str(int(threshold))
                srow["tier_counts"][tkey] = int(srow["tier_counts"].get(tkey, 0)) + 1
                _add_outcome(srow, result=m.result, elo_delta_a=int(m.elo_delta_a or 0))
                active.append(tag)

            active = sorted(set(active))
            if len(active) >= 2:
                for a, b in combinations(active[:6], 2):  # cap to keep it cheap + sane
                    pair = f"{a}+{b}"
                    prow2 = _ensure_row(synergy_pair_rows, rid=pair, name=pair)
                    _add_outcome(
                        prow2, result=m.result, elo_delta_a=int(m.elo_delta_a or 0)
                    )

        portals = _finalize_rows(
            portal_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )
        augments = _finalize_rows(
            augment_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )
        creatures = _finalize_rows(
            creature_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )
        items = _finalize_rows(
            item_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )
        sigils = _finalize_rows(
            sigil_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )
        synergies = _finalize_rows(
            synergy_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )
        synergy_pairs = _finalize_rows(
            synergy_pair_rows,
            total_matches=total,
            low_confidence_min_samples=low_confidence_min_samples,
        )

        portals.sort(key=lambda r: (-int(r["uses"]), str(r["id"])))
        augments.sort(
            key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"]))
        )
        creatures.sort(
            key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"]))
        )
        items.sort(key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"])))
        sigils.sort(key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"])))
        synergies.sort(
            key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"]))
        )
        synergy_pairs.sort(
            key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"]))
        )

        modes[mode] = {
            "matches_total": total,
            "overall": {
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "winrate": overall_wr,
                "avg_elo_delta": avg_elo_delta,
            },
            "portals": portals[:50],
            "augments": augments[:80],
            "creatures": creatures[:60],
            "items": items[:80],
            "sigils": sigils[:40],
            "synergies": synergies[:60],
            "synergy_pairs": synergy_pairs[:40],
        }

    return {
        "generated_at": gen,
        "ruleset_version": ruleset_version,
        "queue_type": queue_type,
        "low_confidence_min_samples": int(low_confidence_min_samples),
        "modes": modes,
    }
