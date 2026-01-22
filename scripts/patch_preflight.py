from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
from typing import Any

import orjson
from sqlalchemy import desc, select

from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal
from neuroleague_api.models import Blueprint
from neuroleague_api.storage_backend import get_storage_backend
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.pack_loader import apply_pack, compute_pack_hash, load_pack
from neuroleague_sim.simulate import simulate_match


def _matchup_id(a_id: str, b_id: str) -> str:
    digest = hashlib.sha256(f"{a_id}|{b_id}".encode("utf-8")).hexdigest()
    return digest[:12]


def _win_score(winner: str) -> float:
    if winner == "A":
        return 1.0
    if winner == "B":
        return 0.0
    return 0.5


def _simulate_winrate(
    *,
    pack_hash: str,
    a_id: str,
    b_id: str,
    spec_a: BlueprintSpec,
    spec_b: BlueprintSpec,
    seed_set_count: int,
) -> float:
    wins = 0.0
    mid = _matchup_id(a_id, b_id)
    match_id = f"pf_{pack_hash[:8]}_{mid}"
    for seed_index in range(int(seed_set_count)):
        replay = simulate_match(
            match_id=match_id,
            seed_index=seed_index,
            blueprint_a=spec_a,
            blueprint_b=spec_b,
        )
        wins += _win_score(replay.end_summary.winner)
    return float(wins) / float(max(1, int(seed_set_count)))


def _load_submitted_blueprints(
    *, db, mode: str, limit: int
) -> list[tuple[str, str, BlueprintSpec]]:
    settings = Settings()
    bps = db.scalars(
        select(Blueprint)
        .where(Blueprint.status == "submitted")
        .where(Blueprint.mode == mode)
        .where(Blueprint.ruleset_version == settings.ruleset_version)
        .order_by(
            desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id.asc()
        )
        .limit(int(limit))
    ).all()
    out: list[tuple[str, str, BlueprintSpec]] = []
    for bp in bps:
        try:
            spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
        except Exception:  # noqa: BLE001
            continue
        out.append((str(bp.id), str(bp.name), spec))
    return out


def _analyze_mode(
    *,
    baseline_pack: dict[str, Any],
    candidate_pack: dict[str, Any],
    mode: str,
    pool_limit: int,
    opponent_limit: int,
    seed_set_count: int,
) -> dict[str, Any]:
    # Build pool from DB (submitted builds). If too small, return empty.
    with SessionLocal() as db:
        pool = _load_submitted_blueprints(db=db, mode=mode, limit=pool_limit)
    if len(pool) < 2:
        return {
            "mode": mode,
            "blueprints": [],
            "matchups_per_blueprint": 0,
            "seed_set_count": seed_set_count,
        }

    # Deterministic opponent selection: pick first N other builds by id order.
    pool_sorted = sorted(pool, key=lambda r: r[0])

    def run(pack: dict[str, Any]) -> dict[str, float]:
        apply_pack(pack)
        ph = compute_pack_hash(pack)
        by_bp: dict[str, float] = {}
        for a_id, _a_name, spec_a in pool_sorted:
            opps = [
                (b_id, spec_b)
                for (b_id, _b_name, spec_b) in pool_sorted
                if b_id != a_id
            ][:opponent_limit]
            if not opps:
                continue
            score = 0.0
            for b_id, spec_b in opps:
                score += _simulate_winrate(
                    pack_hash=ph,
                    a_id=a_id,
                    b_id=b_id,
                    spec_a=spec_a,
                    spec_b=spec_b,
                    seed_set_count=seed_set_count,
                )
            by_bp[a_id] = score / float(len(opps))
        return by_bp

    base_hash = compute_pack_hash(baseline_pack)
    cand_hash = compute_pack_hash(candidate_pack)
    base_rates = run(baseline_pack)
    cand_rates = run(candidate_pack)

    rows = []
    for bp_id, bp_name, _spec in pool_sorted:
        wb = float(base_rates.get(bp_id, 0.0))
        wc = float(cand_rates.get(bp_id, 0.0))
        rows.append(
            {
                "blueprint_id": bp_id,
                "blueprint_name": bp_name,
                "winrate_baseline": wb,
                "winrate_candidate": wc,
                "delta": wc - wb,
            }
        )
    rows.sort(key=lambda r: (-abs(float(r.get("delta") or 0.0)), r["blueprint_id"]))

    return {
        "mode": mode,
        "baseline_pack_hash": base_hash,
        "candidate_pack_hash": cand_hash,
        "pool_size": len(pool_sorted),
        "matchups_per_blueprint": min(opponent_limit, max(0, len(pool_sorted) - 1)),
        "seed_set_count": seed_set_count,
        "top_shifts": rows[:10],
        "blueprints": rows,
    }


def _extract_pack_modifiers(
    pack: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    portals = pack.get("portals") if isinstance(pack.get("portals"), list) else []
    augments = pack.get("augments") if isinstance(pack.get("augments"), list) else []
    if not portals and not augments:
        mods = pack.get("modifiers") if isinstance(pack.get("modifiers"), dict) else {}
        portals = mods.get("portals") if isinstance(mods.get("portals"), list) else []
        augments = (
            mods.get("augments") if isinstance(mods.get("augments"), list) else []
        )

    portal_by_id: dict[str, Any] = {}
    for p in portals:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        portal_by_id[str(p["id"])] = p

    augment_by_id: dict[str, Any] = {}
    for a in augments:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        augment_by_id[str(a["id"])] = a

    return portal_by_id, augment_by_id


def _diff_ids(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, list[str]]:
    base_ids = set(baseline.keys())
    cand_ids = set(candidate.keys())
    added = sorted(cand_ids - base_ids)
    removed = sorted(base_ids - cand_ids)
    changed: list[str] = []
    for _id in sorted(base_ids & cand_ids):
        if orjson.dumps(baseline[_id], option=orjson.OPT_SORT_KEYS) != orjson.dumps(
            candidate[_id], option=orjson.OPT_SORT_KEYS
        ):
            changed.append(str(_id))
    return {"added": added, "removed": removed, "changed": changed}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch preflight: compare baseline vs candidate packs."
    )
    parser.add_argument("--baseline", required=True, help="Path to baseline pack.json")
    parser.add_argument(
        "--candidate", required=True, help="Path to candidate pack.json"
    )
    parser.add_argument("--pool-limit", type=int, default=8)
    parser.add_argument("--opponents", type=int, default=4)
    parser.add_argument("--seed-set-count", type=int, default=3)
    args = parser.parse_args()

    baseline_pack = load_pack(args.baseline)
    candidate_pack = load_pack(args.candidate)

    settings = Settings()
    now = datetime.now(UTC)
    base_portals, base_augments = _extract_pack_modifiers(baseline_pack)
    cand_portals, cand_augments = _extract_pack_modifiers(candidate_pack)
    report: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "ruleset_version": settings.ruleset_version,
        "baseline_pack_hash": compute_pack_hash(baseline_pack),
        "candidate_pack_hash": compute_pack_hash(candidate_pack),
        "pack_changes": {
            "portals": _diff_ids(base_portals, cand_portals),
            "augments": _diff_ids(base_augments, cand_augments),
        },
        "modes": [],
    }

    for mode in ("1v1", "team"):
        report["modes"].append(
            _analyze_mode(
                baseline_pack=baseline_pack,
                candidate_pack=candidate_pack,
                mode=mode,
                pool_limit=int(args.pool_limit),
                opponent_limit=int(args.opponents),
                seed_set_count=int(args.seed_set_count),
            )
        )

    # Write to storage backend under ops/
    backend = get_storage_backend()
    ts = now.strftime("%Y%m%d_%H%M%S")
    json_key = f"ops/preflight_{ts}.json"
    md_key = f"ops/preflight_{ts}.md"

    lines = [
        f"# Patch Preflight ({settings.ruleset_version})",
        f"- generated_at: `{report['generated_at']}`",
        f"- baseline_pack_hash: `{report['baseline_pack_hash']}`",
        f"- candidate_pack_hash: `{report['candidate_pack_hash']}`",
        f"- portal_changes: +{len(report['pack_changes']['portals']['added'])} / -{len(report['pack_changes']['portals']['removed'])} / ~{len(report['pack_changes']['portals']['changed'])}",
        f"- augment_changes: +{len(report['pack_changes']['augments']['added'])} / -{len(report['pack_changes']['augments']['removed'])} / ~{len(report['pack_changes']['augments']['changed'])}",
        "",
    ]
    pc = report.get("pack_changes") or {}
    for label, key in (("Portals", "portals"), ("Augments", "augments")):
        changes = pc.get(key) or {}
        added = changes.get("added") or []
        removed = changes.get("removed") or []
        changed = changes.get("changed") or []
        if not added and not removed and not changed:
            continue
        lines.append(f"## {label} changes")
        if added:
            lines.append(f"- added: {', '.join(str(x) for x in added[:20])}")
        if removed:
            lines.append(f"- removed: {', '.join(str(x) for x in removed[:20])}")
        if changed:
            lines.append(f"- changed: {', '.join(str(x) for x in changed[:20])}")
        lines.append("")
    for mode_report in report["modes"]:
        lines.append(f"## Mode: {mode_report['mode']}")
        lines.append(
            f"- pool_size: {mode_report.get('pool_size', 0)} · matchups_per_blueprint: {mode_report.get('matchups_per_blueprint', 0)} · seed_set_count: {mode_report.get('seed_set_count', 0)}"
        )
        lines.append("")
        for row in mode_report.get("top_shifts") or []:
            lines.append(
                f"- {row['blueprint_id']} ({row['blueprint_name']}): {row['winrate_baseline']:.3f} → {row['winrate_candidate']:.3f} (Δ {row['delta']:+.3f})"
            )
        lines.append("")
    md = "\n".join(lines).encode("utf-8")

    backend.put_bytes(
        key=json_key,
        data=orjson.dumps(report, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )
    backend.put_bytes(key=md_key, data=md, content_type="text/markdown")
    backend.put_bytes(
        key="ops/preflight_latest.json",
        data=orjson.dumps(report, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )
    backend.put_bytes(
        key="ops/preflight_latest.md", data=md, content_type="text/markdown"
    )

    print(f"[patch_preflight] wrote {json_key} and {md_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
