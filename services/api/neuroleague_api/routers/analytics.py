from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
import orjson
from sqlalchemy import desc, nullslast, select
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.elo import division_for_elo
from neuroleague_api.models import Blueprint, Match, Rating, User

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _result_label(result: str) -> Literal["win", "loss", "draw"]:
    if result == "A":
        return "win"
    if result == "B":
        return "loss"
    return "draw"


@router.get("/overview")
def overview(
    mode: Literal["1v1", "team"] = "1v1",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .order_by(Match.created_at)
    ).all()

    wins = sum(1 for m in matches if m.result == "A")
    losses = sum(1 for m in matches if m.result == "B")
    draws = sum(1 for m in matches if m.result == "draw")
    total = len(matches)
    winrate = (wins + 0.5 * draws) / total if total else 0.0
    human_matches = sum(
        1
        for m in matches
        if (m.user_b_id or "") and not str(m.user_b_id).startswith("bot_")
    )
    human_match_rate = human_matches / total if total else 0.0

    rating = db.get(Rating, {"user_id": user_id, "mode": mode})
    elo_current = rating.elo if rating else 1000

    start_elo = elo_current - sum(int(m.elo_delta_a or 0) for m in matches)
    elo = start_elo

    series: list[dict[str, Any]] = []
    for idx, m in enumerate(matches, start=1):
        elo += int(m.elo_delta_a or 0)
        series.append(
            {
                "index": idx,
                "match_id": m.id,
                "at": m.created_at.isoformat(),
                "result": _result_label(m.result),
                "elo": elo,
                "delta": int(m.elo_delta_a or 0),
            }
        )

    recent = list(reversed(series))[:30]
    recent.reverse()

    by_opp: dict[str, dict[str, int]] = {}
    for m in matches:
        opp_name = "Lab_Unknown"
        if m.user_b_id:
            opp = db.get(User, m.user_b_id)
            if opp:
                opp_name = opp.display_name
        row = by_opp.setdefault(
            opp_name, {"matches": 0, "wins": 0, "losses": 0, "draws": 0}
        )
        row["matches"] += 1
        if m.result == "A":
            row["wins"] += 1
        elif m.result == "B":
            row["losses"] += 1
        else:
            row["draws"] += 1

    matchups = []
    for opp, row in by_opp.items():
        mcount = row["matches"]
        wr = (row["wins"] + 0.5 * row["draws"]) / mcount if mcount else 0.0
        matchups.append({"opponent": opp, **row, "winrate": wr})
    matchups.sort(key=lambda r: (-int(r["matches"]), r["opponent"]))

    return {
        "summary": {
            "matches_total": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "winrate": winrate,
            "human_matches": human_matches,
            "human_match_rate": human_match_rate,
            "elo_current": elo_current,
            "division": division_for_elo(elo_current),
        },
        "elo_series": recent,
        "matchups": matchups[:12],
    }


@router.get("/matchups")
def matchups(
    mode: Literal["1v1", "team"] = "1v1",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .order_by(desc(Match.created_at))
        .limit(200)
    ).all()

    by_opp: dict[str, dict[str, Any]] = {}
    for m in matches:
        opp_name = "Lab_Unknown"
        if m.blueprint_b_id:
            opp_bp = db.get(Blueprint, m.blueprint_b_id)
            if opp_bp:
                opp_name = opp_bp.name
        elif m.user_b_id:
            opp = db.get(User, m.user_b_id)
            if opp:
                opp_name = opp.display_name

        row = by_opp.setdefault(
            opp_name,
            {
                "opponent": opp_name,
                "matches": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "sample_match_ids": [],
            },
        )
        row["matches"] += 1
        if m.result == "A":
            row["wins"] += 1
        elif m.result == "B":
            row["losses"] += 1
        else:
            row["draws"] += 1
        if len(row["sample_match_ids"]) < 3:
            row["sample_match_ids"].append(m.id)

    rows = list(by_opp.values())
    for r in rows:
        total = int(r["matches"] or 0)
        r["winrate"] = (
            (int(r["wins"]) + 0.5 * int(r["draws"])) / total if total else 0.0
        )
    rows.sort(key=lambda r: (-int(r["matches"]), str(r["opponent"])))

    return {"rows": rows, "matches_total": len(matches)}


@router.get("/build-insights")
def build_insights(
    mode: Literal["1v1", "team"] = "1v1",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    from neuroleague_sim.catalog import CREATURES

    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .order_by(desc(Match.created_at))
        .limit(200)
    ).all()

    bp_cache: dict[str, dict[str, Any]] = {}

    def outcome(result: str) -> Literal["win", "loss", "draw"]:
        return _result_label(result)

    def add_stat(
        dst: dict[str, dict[str, Any]], key: str, out: Literal["win", "loss", "draw"]
    ) -> None:
        row = dst.setdefault(
            key,
            {"id": key, "uses": 0, "wins": 0, "losses": 0, "draws": 0, "winrate": 0.0},
        )
        row["uses"] += 1
        if out == "win":
            row["wins"] += 1
        elif out == "loss":
            row["losses"] += 1
        else:
            row["draws"] += 1

    item_stats: dict[str, dict[str, Any]] = {}
    synergy_stats: dict[str, dict[str, Any]] = {}

    for m in matches:
        if not m.blueprint_a_id:
            continue
        bp = db.get(Blueprint, m.blueprint_a_id)
        if not bp or bp.user_id != user_id:
            continue
        if bp.id not in bp_cache:
            bp_cache[bp.id] = orjson.loads(bp.spec_json)
        spec = bp_cache[bp.id]
        team = spec.get("team") or []
        tags: list[str] = []
        for slot in team:
            cid = str(slot.get("creature_id") or "")
            if cid and cid in CREATURES:
                tags.extend(list(CREATURES[cid].tags))
            items = slot.get("items") or {}
            for slot_name in ("weapon", "armor", "utility"):
                iid = items.get(slot_name)
                if iid:
                    add_stat(item_stats, str(iid), outcome(m.result))

        counts: dict[str, int] = {}
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
        for tag, count in counts.items():
            if count >= 2:
                add_stat(synergy_stats, tag, outcome(m.result))

    def finalize(dst: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        rows = list(dst.values())
        for r in rows:
            uses = int(r["uses"] or 0)
            r["winrate"] = (
                (int(r["wins"]) + 0.5 * int(r["draws"])) / uses if uses else 0.0
            )
        rows.sort(key=lambda r: (-int(r["uses"]), -float(r["winrate"]), str(r["id"])))
        return rows

    items = finalize(item_stats)
    synergies = finalize(synergy_stats)

    recommendations: list[str] = []
    for row in items[:3]:
        if row["uses"] >= 2:
            recommendations.append(
                f"Item: {row['id']} — winrate {(row['winrate'] * 100):.0f}% over {row['uses']} games"
            )
    for row in synergies[:2]:
        if row["uses"] >= 2:
            recommendations.append(
                f"Synergy: {row['id']} — winrate {(row['winrate'] * 100):.0f}% over {row['uses']} games"
            )
    if not recommendations:
        recommendations.append(
            "Play more ranked matches to unlock stronger build recommendations."
        )

    return {
        "matches_total": len(matches),
        "items": items[:12],
        "synergies": synergies[:12],
        "recommendations": recommendations[:6],
    }


@router.get("/version-compare")
def version_compare(
    blueprint_a_id: str | None = None,
    blueprint_b_id: str | None = None,
    mode: Literal["1v1", "team"] | None = None,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    if not blueprint_a_id or not blueprint_b_id:
        return {"note": "provide blueprint_a_id and blueprint_b_id query params"}

    bp_a = db.get(Blueprint, blueprint_a_id)
    bp_b = db.get(Blueprint, blueprint_b_id)
    if not bp_a or bp_a.user_id != user_id:
        return {"error": "blueprint_a not found"}
    if not bp_b or bp_b.user_id != user_id:
        return {"error": "blueprint_b not found"}
    if bp_a.mode != bp_b.mode:
        return {"error": "blueprint_a and blueprint_b must share the same mode"}
    if mode is not None and mode != bp_a.mode:
        return {"error": "mode query must match blueprint mode"}

    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == bp_a.mode)
        .where(Match.blueprint_a_id.in_([blueprint_a_id, blueprint_b_id]))
        .order_by(desc(Match.created_at))
        .limit(400)
    ).all()

    def opp_key(m: Match) -> str:
        if m.blueprint_b_id:
            bp = db.get(Blueprint, m.blueprint_b_id)
            if bp:
                return bp.name
        if m.user_b_id:
            u = db.get(User, m.user_b_id)
            if u:
                return u.display_name
        return "Lab_Unknown"

    def score(result: str) -> float:
        if result == "A":
            return 1.0
        if result == "B":
            return 0.0
        return 0.5

    agg: dict[str, dict[str, dict[str, Any]]] = {"A": {}, "B": {}}
    overall: dict[str, dict[str, Any]] = {
        "A": {"matches": 0, "score": 0.0},
        "B": {"matches": 0, "score": 0.0},
    }
    for m in matches:
        side = "A" if m.blueprint_a_id == blueprint_a_id else "B"
        key = opp_key(m)
        row = agg[side].setdefault(
            key, {"matches": 0, "score": 0.0, "sample_match_ids": []}
        )
        row["matches"] += 1
        row["score"] += score(m.result)
        if len(row["sample_match_ids"]) < 2:
            row["sample_match_ids"].append(m.id)

        overall[side]["matches"] += 1
        overall[side]["score"] += score(m.result)

    def wr(mcount: int, s: float) -> float:
        return s / mcount if mcount else 0.0

    by_opponent = []
    all_keys = sorted(set(agg["A"].keys()) | set(agg["B"].keys()))
    for key in all_keys:
        a = agg["A"].get(key, {"matches": 0, "score": 0.0, "sample_match_ids": []})
        b = agg["B"].get(key, {"matches": 0, "score": 0.0, "sample_match_ids": []})
        winrate_a = wr(int(a["matches"]), float(a["score"]))
        winrate_b = wr(int(b["matches"]), float(b["score"]))
        by_opponent.append(
            {
                "opponent": key,
                "a": {
                    "matches": int(a["matches"]),
                    "winrate": winrate_a,
                    "sample_match_ids": a["sample_match_ids"],
                },
                "b": {
                    "matches": int(b["matches"]),
                    "winrate": winrate_b,
                    "sample_match_ids": b["sample_match_ids"],
                },
                "delta_winrate": winrate_a - winrate_b,
            }
        )
    by_opponent.sort(
        key=lambda r: (-abs(float(r["delta_winrate"])), str(r["opponent"]))
    )

    overall_a = wr(int(overall["A"]["matches"]), float(overall["A"]["score"]))
    overall_b = wr(int(overall["B"]["matches"]), float(overall["B"]["score"]))
    better = "A" if overall_a > overall_b else "B" if overall_b > overall_a else "tie"
    summary_lines = [
        f"A ({bp_a.name}) winrate: {(overall_a * 100):.0f}% over {overall['A']['matches']} games",
        f"B ({bp_b.name}) winrate: {(overall_b * 100):.0f}% over {overall['B']['matches']} games",
        f"Recommendation: {'Use A' if better == 'A' else 'Use B' if better == 'B' else 'No clear winner yet'}",
    ]

    return {
        "blueprint_a": {"id": bp_a.id, "name": bp_a.name},
        "blueprint_b": {"id": bp_b.id, "name": bp_b.name},
        "summary_lines": summary_lines,
        "by_opponent": by_opponent[:24],
    }


@router.get("/coach")
def coach(
    mode: Literal["1v1", "team"] = "1v1",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    from neuroleague_sim.catalog import CREATURES, ITEMS

    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .order_by(desc(Match.created_at))
        .limit(400)
    ).all()

    if not matches:
        return {
            "mode": mode,
            "cards": [
                {
                    "id": "get-data",
                    "title": "Run a ranked match",
                    "body": f"Analytics coach needs {mode} match data. Queue one match to unlock recommendations.",
                    "evidence": [{"label": "Matches", "value": "0"}],
                    "tags": [mode],
                    "cta": {"label": "Go to Ranked", "href": "/ranked"},
                },
                {
                    "id": "tune-build",
                    "title": "Tune a blueprint",
                    "body": "Draft a new build or tweak items/formation, then validate + submit.",
                    "evidence": [],
                    "tags": ["blueprint", "forge"],
                    "cta": {"label": "Open Forge", "href": "/forge"},
                },
                {
                    "id": "train",
                    "title": "Train a coach (CPU-only)",
                    "body": "Start a short training run to generate a new checkpoint blueprint.",
                    "evidence": [],
                    "tags": ["training", "cpu-only"],
                    "cta": {"label": "Open Training", "href": "/training"},
                },
            ],
        }

    def score(result: str) -> float:
        if result == "A":
            return 1.0
        if result == "B":
            return 0.0
        return 0.5

    wins = sum(1 for m in matches if m.result == "A")
    losses = sum(1 for m in matches if m.result == "B")
    draws = sum(1 for m in matches if m.result == "draw")
    total = len(matches)
    overall_wr = (wins + 0.5 * draws) / total if total else 0.0

    bp_cache: dict[str, dict[str, Any]] = {}

    def load_bp_spec(bp_id: str | None) -> dict[str, Any] | None:
        if not bp_id:
            return None
        if bp_id in bp_cache:
            return bp_cache[bp_id]
        bp = db.get(Blueprint, bp_id)
        if not bp:
            return None
        spec = orjson.loads(bp.spec_json)
        bp_cache[bp_id] = spec
        return spec

    def triggered_synergies(spec: dict[str, Any]) -> list[str]:
        team = spec.get("team") or []
        tags: list[str] = []
        for slot in team:
            cid = str(slot.get("creature_id") or "")
            if cid and cid in CREATURES:
                tags.extend(list(CREATURES[cid].tags))
        counts: dict[str, int] = {}
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
        return [tag for tag, count in counts.items() if count >= 2]

    def synergy_counts_with_bonus(
        spec: dict[str, Any],
    ) -> tuple[dict[str, int], dict[str, int]]:
        team = spec.get("team") or []
        base_counts: dict[str, int] = {}
        bonus_counts: dict[str, int] = {}
        for slot in team:
            cid = str(slot.get("creature_id") or "")
            if cid and cid in CREATURES:
                for tag in CREATURES[cid].tags:
                    base_counts[tag] = base_counts.get(tag, 0) + 1
            items = slot.get("items") or {}
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

    def _pick_sigil_item(tag: str, needed_bonus: int) -> str | None:
        needed_bonus = max(1, int(needed_bonus))
        candidates: list[tuple[int, int, str]] = []
        for iid, idef in ITEMS.items():
            b = int(getattr(idef, "synergy_bonus", {}).get(tag, 0) or 0)
            if b <= 0:
                continue
            rarity = int(getattr(idef, "rarity", 1) or 1)
            candidates.append((rarity, abs(b - needed_bonus), str(iid)))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _synergy_amplify_card() -> dict[str, Any] | None:
        if mode != "team":
            return None

        bp_submitted = db.scalars(
            select(Blueprint)
            .where(Blueprint.user_id == user_id)
            .where(Blueprint.mode == mode)
            .where(Blueprint.status == "submitted")
            .order_by(
                nullslast(desc(Blueprint.submitted_at)), desc(Blueprint.updated_at)
            )
            .limit(1)
        ).first()
        spec_focus = (
            load_bp_spec(bp_submitted.id)
            if bp_submitted
            else load_bp_spec(matches[0].blueprint_a_id)
        )
        if not spec_focus:
            return None

        base_counts, bonus_counts = synergy_counts_with_bonus(spec_focus)

        candidates: list[tuple[int, int, str, int, int, str]] = []
        # Tuple: (target_tier, needed_bonus, tag, base, current, sigil_id)
        for tag, base in base_counts.items():
            base = int(base)
            if base < 2:
                continue
            bonus = int(bonus_counts.get(tag, 0))
            current = base + bonus
            if base >= 3 and current < 4:
                needed = 4 - current
                sigil_id = _pick_sigil_item(tag, needed)
                if sigil_id:
                    candidates.append((4, needed, tag, base, current, sigil_id))
            if base >= 3 and 4 <= current < 6:
                needed = 6 - current
                sigil_id = _pick_sigil_item(tag, 1)
                if sigil_id:
                    candidates.append((6, needed, tag, base, current, sigil_id))

        if not candidates:
            return None

        candidates.sort(key=lambda r: (-int(r[0]), int(r[1]), str(r[2])))
        target_tier, needed, tag, base, current, sigil_id = candidates[0]

        if target_tier == 4:
            title = f"Make {tag} T4 with Sigils"
            body = f"You already have {tag} x{base}. Add {sigil_id} to push it to {tag} T4."
        else:
            title = f"Push {tag} to T6 (stack Sigils)"
            body = (
                f"{tag} is at T4 (x{current}). Add Sigils to reach T6 (need +{needed} more). "
                f"Start with {sigil_id}."
            )

        return {
            "id": "synergy-amplify",
            "title": title,
            "body": body,
            "evidence": [
                {
                    "label": "Current",
                    "value": f"{tag} x{current} (base {base} + bonus {max(0, current - base)})",
                },
                {"label": "Goal", "value": f"{tag} T{target_tier} (need +{needed})"},
            ],
            "tags": [
                f"mode:{mode}",
                f"synergy:{tag}",
                f"item:{sigil_id}",
                f"tier:t{target_tier}",
            ],
            "cta": {"label": "Open Forge", "href": "/forge"},
        }

    def role_key(spec: dict[str, Any]) -> str:
        team = spec.get("team") or []
        if mode != "team":
            slot0 = team[0] if team else {}
            cid = str(slot0.get("creature_id") or "")
            formation = str(slot0.get("formation") or "front")
            role = CREATURES[cid].role if cid in CREATURES else "Unknown"
            return f"{role}:{formation}"
        tanks = 0
        dps = 0
        support = 0
        for slot in team:
            cid = str(slot.get("creature_id") or "")
            role = CREATURES[cid].role if cid in CREATURES else "Unknown"
            if role == "Tank":
                tanks += 1
            elif role == "DPS":
                dps += 1
            elif role == "Support":
                support += 1
        return f"{tanks}T/{dps}D/{support}S"

    # 1) Weak matchup card (opponent)
    by_opp: dict[str, dict[str, Any]] = {}
    opp_synergy_counts: dict[str, dict[str, int]] = {}
    for m in matches:
        opp_name = "Lab_Unknown"
        if m.blueprint_b_id:
            opp_bp = db.get(Blueprint, m.blueprint_b_id)
            if opp_bp:
                opp_name = opp_bp.name
        elif m.user_b_id:
            opp = db.get(User, m.user_b_id)
            if opp:
                opp_name = opp.display_name

        row = by_opp.setdefault(
            opp_name,
            {
                "opponent": opp_name,
                "matches": 0,
                "score": 0.0,
                "sample_loss_match_id": None,
            },
        )
        row["matches"] += 1
        row["score"] += score(m.result)
        if m.result == "B" and not row["sample_loss_match_id"]:
            row["sample_loss_match_id"] = m.id

        spec_b = load_bp_spec(m.blueprint_b_id)
        if spec_b:
            sc = opp_synergy_counts.setdefault(opp_name, {})
            for tag in triggered_synergies(spec_b):
                sc[tag] = sc.get(tag, 0) + 1

    weak_candidates = [
        (opp, r) for opp, r in by_opp.items() if int(r.get("matches") or 0) >= 2
    ]
    if not weak_candidates:
        weak_candidates = list(by_opp.items())
    weak_candidates.sort(
        key=lambda kv: (
            float(kv[1]["score"]) / max(1, int(kv[1]["matches"])),
            -int(kv[1]["matches"]),
            str(kv[0]),
        )
    )
    weak_opp, weak_row = weak_candidates[0]
    weak_wr = float(weak_row["score"]) / max(1, int(weak_row["matches"]))

    top_opp_synergy = None
    sy_counts = opp_synergy_counts.get(weak_opp, {})
    if sy_counts:
        top_opp_synergy = sorted(sy_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][
            0
        ]

    counter_hint = "Adjust items + formation and run a quick benchmark."
    if top_opp_synergy in {"Mystic", "Void", "Crystal"}:
        counter_hint = "Crit-heavy opponent: consider Runic Barrier / Nanofiber Cloak and a sturdier frontline."
    elif top_opp_synergy in {"Mech", "Heavy"}:
        counter_hint = "Tank-heavy opponent: consider Void Dagger / Ember Blade to punch through HP."
    elif top_opp_synergy in {"Beast", "Fire", "Storm"}:
        counter_hint = "Burst opponent: consider Coolant Shell / Reinforced Plate and a Support slot."
    elif top_opp_synergy in {"Knight", "Gelatinous"}:
        counter_hint = (
            "HP-heavy opponent: consider Thorn Spear / Plasma Lance and keep DPS safe."
        )

    weak_card = {
        "id": "weak-matchup",
        "title": f"Weak matchup: {weak_opp}",
        "body": f"Winrate {(weak_wr * 100):.0f}% over {int(weak_row['matches'])} games. {counter_hint}",
        "evidence": [
            {
                "label": "Overall",
                "value": f"{(overall_wr * 100):.0f}% over {total} games",
            },
            {
                "label": "Vs",
                "value": f"{(weak_wr * 100):.0f}% over {int(weak_row['matches'])} games",
            },
        ],
        "tags": [f"mode:{mode}"]
        + ([f"synergy:{top_opp_synergy}"] if top_opp_synergy else []),
        "cta": (
            {
                "label": "Watch a losing replay",
                "href": f"/replay/{weak_row['sample_loss_match_id']}",
            }
            if weak_row.get("sample_loss_match_id")
            else {"label": "Queue a match", "href": "/ranked"}
        ),
    }

    # 2) Underperforming item card (player build)
    item_stats: dict[str, dict[str, Any]] = {}
    synergy_stats: dict[str, dict[str, Any]] = {}
    comp_stats: dict[str, dict[str, Any]] = {}

    def add_outcome(dst: dict[str, dict[str, Any]], key: str, result: str) -> None:
        row = dst.setdefault(key, {"id": key, "uses": 0, "score": 0.0})
        row["uses"] += 1
        row["score"] += score(result)

    for m in matches:
        spec_a = load_bp_spec(m.blueprint_a_id)
        if not spec_a:
            continue
        team = spec_a.get("team") or []
        tags: list[str] = []
        for slot in team:
            cid = str(slot.get("creature_id") or "")
            if cid and cid in CREATURES:
                tags.extend(list(CREATURES[cid].tags))
            items = slot.get("items") or {}
            for slot_name in ("weapon", "armor", "utility"):
                iid = items.get(slot_name)
                if iid:
                    add_outcome(item_stats, str(iid), m.result)

        counts: dict[str, int] = {}
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
        for tag, count in counts.items():
            if count >= 2:
                add_outcome(synergy_stats, tag, m.result)

        add_outcome(comp_stats, role_key(spec_a), m.result)

    def best_and_worst(
        dst: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        rows = []
        for r in dst.values():
            uses = int(r["uses"] or 0)
            if uses < 2:
                continue
            wr = float(r["score"]) / uses if uses else 0.0
            rows.append({**r, "winrate": wr})
        if not rows:
            return None, None
        rows.sort(key=lambda r: (float(r["winrate"]), int(r["uses"]), str(r["id"])))
        worst = rows[0]
        best = rows[-1]
        return best, worst

    amp_card = _synergy_amplify_card()
    best_item, worst_item = best_and_worst(item_stats)
    if amp_card:
        item_card = amp_card
    elif best_item and worst_item and best_item["id"] != worst_item["id"]:
        item_card = {
            "id": "item-swap",
            "title": f"Swap item: {worst_item['id']} → {best_item['id']}",
            "body": (
                f"{worst_item['id']} winrate {(float(worst_item['winrate']) * 100):.0f}% "
                f"over {int(worst_item['uses'])} uses. "
                f"Try {best_item['id']} ({(float(best_item['winrate']) * 100):.0f}% over {int(best_item['uses'])} uses)."
            ),
            "evidence": [
                {
                    "label": "Worst item",
                    "value": f"{worst_item['id']} · {(float(worst_item['winrate']) * 100):.0f}% ({int(worst_item['uses'])})",
                },
                {
                    "label": "Best item",
                    "value": f"{best_item['id']} · {(float(best_item['winrate']) * 100):.0f}% ({int(best_item['uses'])})",
                },
            ],
            "tags": [
                f"mode:{mode}",
                f"item:{worst_item['id']}",
                f"item:{best_item['id']}",
            ],
            "cta": {"label": "Open Forge", "href": "/forge"},
        }
    else:
        best_sy, worst_sy = best_and_worst(synergy_stats)
        if best_sy and worst_sy and best_sy["id"] != worst_sy["id"]:
            item_card = {
                "id": "synergy-shift",
                "title": f"Synergy shift: {worst_sy['id']} → {best_sy['id']}",
                "body": (
                    f"{worst_sy['id']} winrate {(float(worst_sy['winrate']) * 100):.0f}% "
                    f"over {int(worst_sy['uses'])} games. "
                    f"Try enabling {best_sy['id']} ({(float(best_sy['winrate']) * 100):.0f}% over {int(best_sy['uses'])} games)."
                ),
                "evidence": [
                    {
                        "label": "Worst synergy",
                        "value": f"{worst_sy['id']} · {(float(worst_sy['winrate']) * 100):.0f}% ({int(worst_sy['uses'])})",
                    },
                    {
                        "label": "Best synergy",
                        "value": f"{best_sy['id']} · {(float(best_sy['winrate']) * 100):.0f}% ({int(best_sy['uses'])})",
                    },
                ],
                "tags": [
                    f"mode:{mode}",
                    f"synergy:{worst_sy['id']}",
                    f"synergy:{best_sy['id']}",
                ],
                "cta": {"label": "Open Forge", "href": "/forge"},
            }
        else:
            item_card = {
                "id": "insights",
                "title": "Collect more build insights",
                "body": "Play a few more matches with different items/synergies to unlock stronger suggestions.",
                "evidence": [{"label": "Matches", "value": str(total)}],
                "tags": [f"mode:{mode}"],
                "cta": {"label": "Queue a match", "href": "/ranked"},
            }

    # 3) Formation / composition card
    comp_rows = []
    for r in comp_stats.values():
        uses = int(r["uses"] or 0)
        wr = float(r["score"]) / uses if uses else 0.0
        comp_rows.append({**r, "winrate": wr})
    comp_rows.sort(key=lambda r: (-int(r["uses"]), str(r["id"])))
    most_used = comp_rows[0] if comp_rows else None
    best_comp = (
        max(comp_rows, key=lambda r: (float(r["winrate"]), int(r["uses"])))
        if comp_rows
        else None
    )

    if (
        most_used
        and best_comp
        and most_used["id"] != best_comp["id"]
        and int(best_comp["uses"]) >= 2
    ):
        comp_card = {
            "id": "composition",
            "title": "Try a different lineup",
            "body": (
                f"Most played: {most_used['id']} ({(float(most_used['winrate']) * 100):.0f}% over {int(most_used['uses'])}). "
                f"Best seen: {best_comp['id']} ({(float(best_comp['winrate']) * 100):.0f}% over {int(best_comp['uses'])})."
            ),
            "evidence": [
                {
                    "label": "Most played",
                    "value": f"{most_used['id']} · {(float(most_used['winrate']) * 100):.0f}% ({int(most_used['uses'])})",
                },
                {
                    "label": "Best seen",
                    "value": f"{best_comp['id']} · {(float(best_comp['winrate']) * 100):.0f}% ({int(best_comp['uses'])})",
                },
            ],
            "tags": [f"mode:{mode}"],
            "cta": {"label": "Open Forge", "href": "/forge"},
        }
    else:
        comp_card = {
            "id": "benchmark",
            "title": "Benchmark a checkpoint",
            "body": "Use Training → Benchmark to compare matchups vs fixed bots before submitting to ranked.",
            "evidence": [
                {"label": "Overall winrate", "value": f"{(overall_wr * 100):.0f}%"}
            ],
            "tags": [f"mode:{mode}", "benchmark"],
            "cta": {"label": "Open Training", "href": "/training"},
        }

    return {
        "mode": mode,
        "summary": {
            "matches_total": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "winrate": overall_wr,
        },
        "cards": [weak_card, item_card, comp_card],
    }


@router.get("/modifiers")
def modifiers(
    mode: Literal["1v1", "team"] = "1v1",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    from neuroleague_sim.modifiers import AUGMENTS, PORTALS

    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .order_by(desc(Match.created_at))
        .limit(500)
    ).all()

    portals: dict[str, dict[str, Any]] = {}
    augments: dict[str, dict[str, Any]] = {}

    def ensure_portal(pid: str) -> dict[str, Any]:
        row = portals.get(pid)
        if row:
            return row
        pdef = PORTALS.get(pid)
        row = {
            "portal_id": pid,
            "portal_name": pdef.name if pdef else pid,
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "winrate": 0.0,
        }
        portals[pid] = row
        return row

    def ensure_augment(aid: str) -> dict[str, Any]:
        row = augments.get(aid)
        if row:
            return row
        adef = AUGMENTS.get(aid)
        row = {
            "augment_id": aid,
            "augment_name": adef.name if adef else aid,
            "tier": int(adef.tier) if adef else None,
            "category": adef.category if adef else None,
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "winrate": 0.0,
        }
        augments[aid] = row
        return row

    for m in matches:
        pid = str(getattr(m, "portal_id", None) or "legacy")
        prow = ensure_portal(pid)
        prow["matches"] += 1
        if m.result == "A":
            prow["wins"] += 1
        elif m.result == "B":
            prow["losses"] += 1
        else:
            prow["draws"] += 1

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
                arow = ensure_augment(aid)
                arow["matches"] += 1
                if m.result == "A":
                    arow["wins"] += 1
                elif m.result == "B":
                    arow["losses"] += 1
                else:
                    arow["draws"] += 1

    for row in portals.values():
        total = int(row["matches"] or 0)
        row["winrate"] = (
            (int(row["wins"]) + 0.5 * int(row["draws"])) / total if total else 0.0
        )
    for row in augments.values():
        total = int(row["matches"] or 0)
        row["winrate"] = (
            (int(row["wins"]) + 0.5 * int(row["draws"])) / total if total else 0.0
        )

    portal_rows = list(portals.values())
    portal_rows.sort(key=lambda r: (-int(r["matches"]), str(r["portal_id"])))
    augment_rows = list(augments.values())
    augment_rows.sort(
        key=lambda r: (-int(r["matches"]), -float(r["winrate"]), str(r["augment_id"]))
    )

    return {
        "mode": mode,
        "matches_total": len(matches),
        "portals": portal_rows,
        "augments": augment_rows[:50],
    }


def _parse_days(range_raw: str | None) -> int:
    raw = str(range_raw or "7d").strip().lower()
    if raw.endswith("d"):
        raw = raw[:-1]
    try:
        days = int(raw)
    except Exception:  # noqa: BLE001
        return 7
    return max(1, min(365, days))


@router.get("/portals")
def portals(
    mode: Literal["1v1", "team"] = "1v1",
    range: str = "7d",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    from neuroleague_sim.modifiers import PORTALS

    days = _parse_days(range)
    since = datetime.now(UTC) - timedelta(days=days)
    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .where(Match.created_at >= since)
        .order_by(desc(Match.created_at))
        .limit(1000)
    ).all()

    portals: dict[str, dict[str, Any]] = {}
    for m in matches:
        pid = str(getattr(m, "portal_id", None) or "legacy")
        row = portals.get(pid)
        if not row:
            pdef = PORTALS.get(pid)
            row = {
                "portal_id": pid,
                "portal_name": pdef.name if pdef else pid,
                "matches": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "winrate": 0.0,
                "sample_match_ids": [],
            }
            portals[pid] = row

        row["matches"] += 1
        if m.result == "A":
            row["wins"] += 1
        elif m.result == "B":
            row["losses"] += 1
        else:
            row["draws"] += 1
        if len(row["sample_match_ids"]) < 3:
            row["sample_match_ids"].append(m.id)

    rows = list(portals.values())
    for r in rows:
        total = int(r["matches"] or 0)
        r["winrate"] = (
            (int(r["wins"]) + 0.5 * int(r["draws"])) / total if total else 0.0
        )
    rows.sort(key=lambda r: (-int(r["matches"]), str(r["portal_id"])))

    return {
        "mode": mode,
        "range": f"{days}d",
        "matches_total": len(matches),
        "portals": rows,
    }


@router.get("/augments")
def augments(
    mode: Literal["1v1", "team"] = "1v1",
    range: str = "7d",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    from neuroleague_sim.modifiers import AUGMENTS

    days = _parse_days(range)
    since = datetime.now(UTC) - timedelta(days=days)
    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .where(Match.created_at >= since)
        .order_by(desc(Match.created_at))
        .limit(1000)
    ).all()

    augments: dict[str, dict[str, Any]] = {}
    for m in matches:
        try:
            aug_a = orjson.loads(getattr(m, "augments_a_json", "[]") or "[]")
        except Exception:  # noqa: BLE001
            aug_a = []
        if not isinstance(aug_a, list):
            continue
        for entry in aug_a:
            if not isinstance(entry, dict):
                continue
            aid = str(entry.get("augment_id") or "")
            if not aid:
                continue
            row = augments.get(aid)
            if not row:
                adef = AUGMENTS.get(aid)
                row = {
                    "augment_id": aid,
                    "augment_name": adef.name if adef else aid,
                    "tier": int(adef.tier) if adef else None,
                    "category": adef.category if adef else None,
                    "matches": 0,
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "winrate": 0.0,
                    "sample_match_ids": [],
                }
                augments[aid] = row

            row["matches"] += 1
            if m.result == "A":
                row["wins"] += 1
            elif m.result == "B":
                row["losses"] += 1
            else:
                row["draws"] += 1
            if len(row["sample_match_ids"]) < 3:
                row["sample_match_ids"].append(m.id)

    rows = list(augments.values())
    for r in rows:
        total = int(r["matches"] or 0)
        r["winrate"] = (
            (int(r["wins"]) + 0.5 * int(r["draws"])) / total if total else 0.0
        )
    rows.sort(
        key=lambda r: (-int(r["matches"]), -float(r["winrate"]), str(r["augment_id"]))
    )

    return {
        "mode": mode,
        "range": f"{days}d",
        "matches_total": len(matches),
        "augments": rows[:100],
    }
