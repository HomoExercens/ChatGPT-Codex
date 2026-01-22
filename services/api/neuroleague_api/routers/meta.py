from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import orjson
from fastapi import APIRouter

from neuroleague_api.core.config import Settings
from neuroleague_api.storage_backend import get_storage_backend

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/patch-notes")
def patch_notes() -> dict:
    notes = [
        {
            "version": "ruleset 2026S1-v1",
            "date": "Today",
            "title": "Deterministic sim baseline locked.",
        },
        {
            "version": "local-dev",
            "date": "Today",
            "title": "Seeded demo blueprints and a bot opponent.",
        },
    ]

    try:
        backend = get_storage_backend()
        key = "ops/patch_notes.json"
        if backend.exists(key=key):
            raw = backend.get_bytes(key=key)
            parsed = orjson.loads(raw)
            extra: list[dict] = []
            if isinstance(parsed, dict) and isinstance(parsed.get("notes"), list):
                extra = [n for n in parsed["notes"] if isinstance(n, dict)]
            elif isinstance(parsed, list):
                extra = [n for n in parsed if isinstance(n, dict)]
            seen = {
                (str(n.get("version")), str(n.get("date")), str(n.get("title")))
                for n in notes
            }
            for n in extra:
                key_t = (str(n.get("version")), str(n.get("date")), str(n.get("title")))
                if key_t in seen:
                    continue
                seen.add(key_t)
                notes.append(n)
    except Exception:  # noqa: BLE001
        pass

    return {"notes": notes}


@router.get("/archetypes/top")
def archetypes_top() -> dict:
    return {"archetypes": [{"id": "mech_rush", "name": "Mech Rush", "winrate": 0.542}]}


@router.get("/season")
def season() -> dict:
    settings = Settings()
    return {
        "season_name": "2026 S1",
        "ruleset_version": settings.ruleset_version,
        "patch_notes": patch_notes().get("notes", []),
    }


@router.get("/flags")
def flags() -> dict:
    settings = Settings()
    return {
        "demo_mode": bool(settings.demo_mode),
        "log_json": bool(settings.log_json),
        "alerts_enabled": bool(settings.alerts_enabled),
        "steam_app_id": settings.steam_app_id,
        "discord_invite_url": settings.discord_invite_url,
    }


@router.get("/modifiers")
def modifiers() -> dict:
    from neuroleague_sim.modifiers import augments_public, portal_public

    return {"portals": portal_public(), "augments": augments_public()}


@router.get("/portals")
def portals() -> dict:
    from neuroleague_sim.modifiers import portal_public

    return {"portals": portal_public()}


@router.get("/augments")
def augments() -> dict:
    from neuroleague_sim.modifiers import augments_public

    return {"augments": augments_public()}


def _iso_week_id(dt: datetime) -> str:
    year, week, _weekday = dt.isocalendar()
    return f"{int(year)}W{int(week):02d}"


def _pick_stable(seed: str, ids: list[str], k: int) -> list[str]:
    scored = []
    for _id in sorted(ids):
        h = hashlib.sha256(f"{seed}:{_id}".encode("utf-8")).hexdigest()
        scored.append((h, _id))
    scored.sort(key=lambda t: t[0])
    return [_id for (_h, _id) in scored[: max(0, int(k))]]


@router.get("/weekly")
def weekly(week_id: str | None = None) -> dict:
    settings = Settings()
    now = datetime.now(UTC)
    wid = week_id or _iso_week_id(now)

    override: dict | None = None
    try:
        backend = get_storage_backend()
        key = "ops/weekly_theme_override.json"
        if backend.exists(key=key):
            override_raw = backend.get_bytes(key=key)
            override = orjson.loads(override_raw)
    except Exception:  # noqa: BLE001
        override = None

    from neuroleague_sim.modifiers import augments_public, portal_public

    portals = portal_public()
    augments = augments_public()
    portal_by_id = {p["id"]: p for p in portals if isinstance(p, dict) and p.get("id")}
    augment_by_id = {
        a["id"]: a for a in augments if isinstance(a, dict) and a.get("id")
    }

    seed = f"{settings.ruleset_version}:{wid}"

    if isinstance(override, dict) and (override.get("week_id") == wid):
        featured_portal_ids = [
            str(x)
            for x in (override.get("featured_portal_ids") or [])
            if str(x) in portal_by_id
        ]
        featured_augment_ids = [
            str(x)
            for x in (override.get("featured_augment_ids") or [])
            if str(x) in augment_by_id
        ]
        name = str(override.get("name") or f"Weekly Theme {wid}")
        description = str(override.get("description") or "")
        tournament_rules = override.get("tournament_rules") or {}
    else:
        portal_ids = list(portal_by_id.keys())
        featured_portal_ids = _pick_stable(seed + ":portals", portal_ids, 3)
        aug_by_tier: dict[int, list[str]] = {}
        for aid, adef in augment_by_id.items():
            try:
                tier = int(adef.get("tier") or 1)  # type: ignore[call-arg]
            except Exception:  # noqa: BLE001
                tier = 1
            aug_by_tier.setdefault(tier, []).append(str(aid))
        featured_augment_ids = (
            _pick_stable(seed + ":aug_t1", aug_by_tier.get(1, []), 4)
            + _pick_stable(seed + ":aug_t2", aug_by_tier.get(2, []), 4)
            + _pick_stable(seed + ":aug_t3", aug_by_tier.get(3, []), 4)
        )
        primary_portal = (
            portal_by_id.get(featured_portal_ids[0]) if featured_portal_ids else None
        )
        name = f"{wid} — {primary_portal.get('name') if primary_portal else 'Open Lab'}"
        description = "Featured portal & augment pool rotates weekly (deterministic ISO-week seed)."
        tournament_rules = {"matches_counted": 10, "queue_open": True}

    featured_portals = [
        portal_by_id[i] for i in featured_portal_ids if i in portal_by_id
    ]
    featured_augments = [
        augment_by_id[i] for i in featured_augment_ids if i in augment_by_id
    ]

    return {
        "week_id": wid,
        "name": name,
        "description": description,
        "featured_portals": featured_portals,
        "featured_augments": featured_augments,
        "tournament_rules": tournament_rules,
    }
