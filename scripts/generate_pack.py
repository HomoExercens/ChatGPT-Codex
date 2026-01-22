from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from neuroleague_sim import catalog as catalog_mod
from neuroleague_sim import modifiers as modifiers_mod
from neuroleague_sim.pack_loader import compute_pack_hash


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_pack(*, ruleset_version: str) -> dict[str, Any]:
    creatures = []
    for cid in sorted(catalog_mod.CREATURES.keys()):
        c = catalog_mod.CREATURES[cid]
        creatures.append(
            {
                "id": c.id,
                "name": c.name,
                "role": c.role,
                "range": c.range,
                "tags": list(c.tags),
                "max_hp": int(c.max_hp),
                "atk": int(c.atk),
                "attack_interval_ticks": int(c.attack_interval_ticks),
                "heal_interval_ticks": int(c.heal_interval_ticks)
                if c.heal_interval_ticks is not None
                else None,
                "rarity": int(c.rarity),
            }
        )

    items = []
    for iid in sorted(catalog_mod.ITEMS.keys()):
        it = catalog_mod.ITEMS[iid]
        items.append(
            {
                "id": it.id,
                "slot": it.slot,
                "name": it.name,
                "rarity": int(it.rarity),
                "atk_permille": int(it.atk_permille),
                "hp_permille": int(it.hp_permille),
                "crit_permille": int(it.crit_permille),
                "damage_reduction_permille": int(it.damage_reduction_permille),
                "speed_permille": int(it.speed_permille),
                "synergy_bonus": {
                    k: int(v) for k, v in (it.synergy_bonus or {}).items()
                },
                "badge_text": it.badge_text,
            }
        )

    synergies: dict[str, Any] = {}
    for tag in sorted(catalog_mod.SYNERGY_EFFECTS.keys()):
        thresholds = catalog_mod.SYNERGY_EFFECTS[tag]
        synergies[tag] = {
            str(int(th)): dict(eff) for th, eff in sorted(thresholds.items())
        }

    portals = []
    for pid in sorted(modifiers_mod.PORTALS.keys()):
        p = modifiers_mod.PORTALS[pid]
        portals.append(
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "rules_json": p.rules_json,
                "rarity": int(getattr(p, "rarity", 1) or 1),
                "tags": list(getattr(p, "tags", ()) or ()),
            }
        )

    augments = []
    for aid in sorted(modifiers_mod.AUGMENTS.keys()):
        a = modifiers_mod.AUGMENTS[aid]
        augments.append(
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "tier": int(a.tier),
                "category": a.category,
                "rules_json": a.rules_json,
                "tags": list(getattr(a, "tags", ()) or ()),
            }
        )

    pack: dict[str, Any] = {
        "pack_version": "default/v1",
        "ruleset_version": str(ruleset_version),
        "created_at": datetime.now(UTC).isoformat(),
        "catalog": {"creatures": creatures, "items": items},
        "synergies": {"effects": synergies},
        "portals": portals,
        "augments": augments,
        "tuning": {},
        "cosmetics": [],
    }
    pack["pack_hash"] = compute_pack_hash(pack)
    return pack


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate packs/default/v1/pack.json from current sim content."
    )
    parser.add_argument(
        "--out", default=None, help="Output path (default packs/default/v1/pack.json)"
    )
    parser.add_argument("--ruleset-version", default="2026S1-v1")
    args = parser.parse_args()

    out_path = (
        Path(args.out)
        if args.out
        else (_repo_root() / "packs" / "default" / "v1" / "pack.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pack = build_pack(ruleset_version=str(args.ruleset_version))

    # Preserve created_at if file exists (avoid noisy diffs).
    if out_path.exists():
        try:
            existing = orjson.loads(out_path.read_bytes())
            if isinstance(existing, dict) and isinstance(
                existing.get("created_at"), str
            ):
                pack["created_at"] = existing["created_at"]
        except Exception:  # noqa: BLE001
            pass

    out_path.write_bytes(
        orjson.dumps(pack, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )
    print(f"[generate_pack] wrote {out_path} (pack_hash={pack['pack_hash']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
