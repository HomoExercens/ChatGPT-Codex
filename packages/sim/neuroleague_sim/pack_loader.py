from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import orjson


_ACTIVE_PACK: dict[str, Any] | None = None
_ACTIVE_PACK_HASH: str | None = None
_ACTIVE_PACK_PATH: Path | None = None


def _repo_root() -> Path:
    # packages/sim/neuroleague_sim -> repo root is 3 levels up
    return Path(__file__).resolve().parents[3]


def _canonical_pack_bytes(pack: dict[str, Any]) -> bytes:
    # Exclude metadata fields that should not affect determinism.
    obj = dict(pack)
    obj.pop("pack_hash", None)
    obj.pop("created_at", None)
    return orjson.dumps(obj, option=orjson.OPT_SORT_KEYS)


def compute_pack_hash(pack: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_pack_bytes(pack)).hexdigest()


def load_pack(path: str | os.PathLike[str]) -> dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    obj = orjson.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("pack must be a JSON object")
    return obj


def _pack_path_for_ruleset(ruleset_version: str) -> Path:
    root = _repo_root() / "packs"
    rs = str(ruleset_version or "").strip()
    if rs:
        direct = root / rs / "pack.json"
        if direct.exists():
            return direct
        versioned = root / rs / "v1" / "pack.json"
        if versioned.exists():
            return versioned
    return root / "default" / "v1" / "pack.json"


def load_active_pack(
    *, force_reload: bool = False, apply: bool = True
) -> dict[str, Any] | None:
    global _ACTIVE_PACK, _ACTIVE_PACK_HASH, _ACTIVE_PACK_PATH

    if _ACTIVE_PACK is not None and not force_reload:
        return _ACTIVE_PACK

    ruleset = (
        str(os.environ.get("NEUROLEAGUE_ACTIVE_RULESET_VERSION") or "").strip()
        or str(os.environ.get("ACTIVE_RULESET_VERSION") or "").strip()
    )
    if not ruleset:
        ruleset = (
            str(os.environ.get("NEUROLEAGUE_RULESET_VERSION") or "").strip()
            or "2026S1-v1"
        )

    path = _pack_path_for_ruleset(ruleset)
    if not path.exists():
        _ACTIVE_PACK = None
        _ACTIVE_PACK_HASH = None
        _ACTIVE_PACK_PATH = None
        return None

    pack = load_pack(path)
    computed = compute_pack_hash(pack)
    declared = str(pack.get("pack_hash") or "").strip()
    if declared and declared != computed:
        raise ValueError(
            f"pack_hash mismatch for {path}: declared={declared} computed={computed}"
        )

    _ACTIVE_PACK = pack
    _ACTIVE_PACK_HASH = computed
    _ACTIVE_PACK_PATH = path

    if apply:
        apply_pack(pack)

    return pack


def active_pack_hash() -> str | None:
    if _ACTIVE_PACK_HASH is not None:
        return _ACTIVE_PACK_HASH
    pack = load_active_pack(apply=True)
    if pack is None:
        return None
    return _ACTIVE_PACK_HASH


def active_pack_path() -> str | None:
    global _ACTIVE_PACK_PATH
    if _ACTIVE_PACK_PATH is not None:
        return str(_ACTIVE_PACK_PATH)
    pack = load_active_pack(apply=True)
    if pack is None or _ACTIVE_PACK_PATH is None:
        return None
    return str(_ACTIVE_PACK_PATH)


def find_pack_path_by_hash(pack_hash: str) -> Path | None:
    root = _repo_root() / "packs"
    if not root.exists():
        return None
    for p in sorted(root.rglob("pack.json")):
        try:
            pack = load_pack(p)
            if compute_pack_hash(pack) == str(pack_hash):
                return p
        except Exception:  # noqa: BLE001
            continue
    return None


def apply_pack(pack: dict[str, Any]) -> None:
    global _ACTIVE_PACK, _ACTIVE_PACK_HASH
    # Apply in-place so other imports keep working.
    from neuroleague_sim import catalog as catalog_mod
    from neuroleague_sim.catalog import CreatureDef, ItemDef
    from neuroleague_sim import modifiers as modifiers_mod
    from neuroleague_sim.modifiers import AugmentDef, PortalDef

    cat = pack.get("catalog") if isinstance(pack.get("catalog"), dict) else {}
    creatures = cat.get("creatures") if isinstance(cat.get("creatures"), list) else []
    items = cat.get("items") if isinstance(cat.get("items"), list) else []

    new_creatures: dict[str, CreatureDef] = {}
    for c in creatures:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        cid = str(c["id"])
        tags = c.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tag_tuple = tuple(str(t) for t in tags[:2])
        if len(tag_tuple) != 2:
            continue
        new_creatures[cid] = CreatureDef(
            id=cid,
            name=str(c.get("name") or cid),
            role=str(c.get("role") or "DPS"),  # type: ignore[arg-type]
            range=str(c.get("range") or "melee"),  # type: ignore[arg-type]
            tags=tag_tuple,  # type: ignore[arg-type]
            max_hp=int(c.get("max_hp") or 1),
            atk=int(c.get("atk") or 1),
            attack_interval_ticks=int(c.get("attack_interval_ticks") or 20),
            heal_interval_ticks=int(c["heal_interval_ticks"])
            if c.get("heal_interval_ticks") is not None
            else None,
            rarity=int(c.get("rarity") or 1),
        )

    new_items: dict[str, ItemDef] = {}
    for it in items:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        iid = str(it["id"])
        synergy_bonus = it.get("synergy_bonus")
        if not isinstance(synergy_bonus, dict):
            synergy_bonus = {}
        new_items[iid] = ItemDef(
            id=iid,
            slot=str(it.get("slot") or "utility"),  # type: ignore[arg-type]
            name=str(it.get("name") or iid),
            rarity=int(it.get("rarity") or 1),
            atk_permille=int(it.get("atk_permille") or 0),
            hp_permille=int(it.get("hp_permille") or 0),
            crit_permille=int(it.get("crit_permille") or 0),
            damage_reduction_permille=int(it.get("damage_reduction_permille") or 0),
            speed_permille=int(it.get("speed_permille") or 0),
            synergy_bonus={
                str(k): int(v) for k, v in synergy_bonus.items() if int(v or 0) != 0
            },
            badge_text=str(it.get("badge_text"))
            if it.get("badge_text") is not None
            else None,
        )

    # Update in place for determinism.
    catalog_mod.CREATURES.clear()
    for cid in sorted(new_creatures.keys()):
        catalog_mod.CREATURES[cid] = new_creatures[cid]

    catalog_mod.ITEMS.clear()
    for iid in sorted(new_items.keys()):
        catalog_mod.ITEMS[iid] = new_items[iid]

    # Rebuild rarity maps.
    catalog_mod.CREATURES_BY_RARITY.clear()
    for cid, cdef in catalog_mod.CREATURES.items():
        catalog_mod.CREATURES_BY_RARITY.setdefault(int(cdef.rarity), []).append(cid)
    for rarity, ids in catalog_mod.CREATURES_BY_RARITY.items():
        ids.sort()

    catalog_mod.ITEMS_BY_RARITY_SLOT.clear()
    for iid, idef in catalog_mod.ITEMS.items():
        slot = str(idef.slot)
        catalog_mod.ITEMS_BY_RARITY_SLOT.setdefault(slot, {}).setdefault(
            int(idef.rarity), []
        ).append(iid)
    for slot, by_rarity in catalog_mod.ITEMS_BY_RARITY_SLOT.items():
        for rarity, ids in by_rarity.items():
            ids.sort()

    # Synergy effects thresholds.
    synergies = pack.get("synergies") if isinstance(pack.get("synergies"), dict) else {}
    effects = (
        synergies.get("effects") if isinstance(synergies.get("effects"), dict) else {}
    )
    new_effects: dict[str, dict[int, dict[str, int]]] = {}
    for tag, thresholds in effects.items():
        if not isinstance(thresholds, dict):
            continue
        th_out: dict[int, dict[str, int]] = {}
        for th, eff in thresholds.items():
            try:
                th_i = int(th)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(eff, dict):
                continue
            th_out[th_i] = {str(k): int(v) for k, v in eff.items()}
        if th_out:
            new_effects[str(tag)] = th_out
    catalog_mod.SYNERGY_EFFECTS.clear()
    for tag in sorted(new_effects.keys()):
        catalog_mod.SYNERGY_EFFECTS[tag] = new_effects[tag]

    # Modifiers: portals/augments
    #
    # Pack schema v1: `modifiers.portals[]` / `modifiers.augments[]`
    # Pack schema v2: top-level `portals[]` / `augments[]`
    portals = pack.get("portals") if isinstance(pack.get("portals"), list) else []
    augments = pack.get("augments") if isinstance(pack.get("augments"), list) else []
    if not portals and not augments:
        mods = pack.get("modifiers") if isinstance(pack.get("modifiers"), dict) else {}
        portals = mods.get("portals") if isinstance(mods.get("portals"), list) else []
        augments = (
            mods.get("augments") if isinstance(mods.get("augments"), list) else []
        )

    new_portals: dict[str, PortalDef] = {}
    for p in portals:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        pid = str(p["id"])
        tags = p.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        rules_json = p.get("rules_json")
        if not isinstance(rules_json, dict):
            rules_json = {}
        new_portals[pid] = PortalDef(
            id=pid,
            name=str(p.get("name") or pid),
            description=str(p.get("description") or ""),
            rules_json=rules_json,
            rarity=int(p.get("rarity") or 1),
            tags=tuple(str(t) for t in tags),
        )

    new_augments: dict[str, AugmentDef] = {}
    for a in augments:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        aid = str(a["id"])
        tags = a.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        rules_json = a.get("rules_json")
        if not isinstance(rules_json, dict):
            rules_json = {}
        new_augments[aid] = AugmentDef(
            id=aid,
            name=str(a.get("name") or aid),
            description=str(a.get("description") or ""),
            tier=int(a.get("tier") or 1),
            category=str(a.get("category") or "combat"),
            rules_json=rules_json,
            tags=tuple(str(t) for t in tags),
        )

    modifiers_mod.PORTALS.clear()
    for pid in sorted(new_portals.keys()):
        modifiers_mod.PORTALS[pid] = new_portals[pid]

    modifiers_mod.AUGMENTS.clear()
    for aid in sorted(new_augments.keys()):
        modifiers_mod.AUGMENTS[aid] = new_augments[aid]

    # Mark as the active pack for replay headers and cache keys.
    _ACTIVE_PACK = pack
    _ACTIVE_PACK_HASH = compute_pack_hash(pack)
