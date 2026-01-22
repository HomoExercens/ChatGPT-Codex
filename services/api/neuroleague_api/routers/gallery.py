from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import orjson
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.build_code import encode_build_code
from neuroleague_api.build_of_day import (
    load_build_of_day_overrides,
    resolve_build_of_day,
    kst_date_key,
)
from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Blueprint, Match, ModerationHide, User
from neuroleague_sim.catalog import CREATURES
from neuroleague_sim.models import BlueprintSpec

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


def _active_pack_hash() -> str | None:
    try:
        from neuroleague_sim.pack_loader import active_pack_hash

        return active_pack_hash()
    except Exception:  # noqa: BLE001
        return None


class GalleryUserOut(BaseModel):
    user_id: str
    display_name: str


class GalleryStatsOut(BaseModel):
    matches: int
    wins: int
    losses: int
    draws: int
    winrate: float
    avg_elo_delta: float
    last_played_at: datetime | None = None


class GalleryBlueprintRowOut(BaseModel):
    blueprint_id: str
    name: str
    mode: Literal["1v1", "team"]
    ruleset_version: str
    spec_hash: str
    submitted_at: datetime | None = None
    build_code: str | None = None
    forked_from_id: str | None = None
    creator: GalleryUserOut
    synergy_tags: list[str]
    stats: GalleryStatsOut


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _extract_synergy_tags(spec: BlueprintSpec) -> list[str]:
    tags: set[str] = set()
    for slot in spec.team:
        cid = (
            slot.get("creature_id")
            if isinstance(slot, dict)
            else getattr(slot, "creature_id", None)
        )
        cdef = CREATURES.get(str(cid))
        if not cdef:
            continue
        tags.add(str(cdef.tags[0]))
        tags.add(str(cdef.tags[1]))
    return sorted(tags)


def _stats_for_blueprints(
    db: Session,
    *,
    blueprint_ids: list[str],
    mode: Literal["1v1", "team"],
    ruleset_version: str,
) -> dict[str, dict[str, Any]]:
    if not blueprint_ids:
        return {}

    matches = db.scalars(
        select(Match)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .where(Match.ruleset_version == ruleset_version)
        .where(
            (Match.blueprint_a_id.in_(blueprint_ids))
            | (Match.blueprint_b_id.in_(blueprint_ids))
        )
        .order_by(desc(Match.finished_at), desc(Match.created_at), Match.id.asc())
    ).all()

    out: dict[str, dict[str, Any]] = {}
    for bid in blueprint_ids:
        out[bid] = {
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "elo_sum": 0,
            "last_played_at": None,
        }

    for m in matches:
        finished_at = _as_aware(m.finished_at) or _as_aware(m.created_at)
        if m.blueprint_a_id in out:
            s = out[m.blueprint_a_id]
            s["matches"] += 1
            s["elo_sum"] += int(m.elo_delta_a or 0)
            s["last_played_at"] = s["last_played_at"] or finished_at
            if m.result == "A":
                s["wins"] += 1
            elif m.result == "B":
                s["losses"] += 1
            else:
                s["draws"] += 1
        if m.blueprint_b_id in out:
            s = out[m.blueprint_b_id]
            s["matches"] += 1
            s["elo_sum"] += int(m.elo_delta_b or 0)
            s["last_played_at"] = s["last_played_at"] or finished_at
            if m.result == "B":
                s["wins"] += 1
            elif m.result == "A":
                s["losses"] += 1
            else:
                s["draws"] += 1

    return out


def _compute_build_code(bp: Blueprint) -> str | None:
    try:
        spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
        return encode_build_code(spec=spec, pack_hash=_active_pack_hash())
    except Exception:  # noqa: BLE001
        return None


def _gallery_row_for_blueprint_id(
    db: Session,
    *,
    blueprint_id: str,
    mode: Literal["1v1", "team"],
    ruleset_version: str,
) -> GalleryBlueprintRowOut | None:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.status != "submitted":
        return None
    if str(bp.mode) != str(mode) or str(bp.ruleset_version) != str(ruleset_version):
        return None
    if str(bp.user_id or "").startswith("bot_"):
        return None
    hidden = db.scalar(
        select(ModerationHide.target_id)
        .where(ModerationHide.target_type == "build")
        .where(ModerationHide.target_id == blueprint_id)
        .limit(1)
    )
    if hidden is not None:
        return None

    try:
        spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
    except Exception:  # noqa: BLE001
        return None
    tags = _extract_synergy_tags(spec)

    stats_map = _stats_for_blueprints(
        db, blueprint_ids=[bp.id], mode=mode, ruleset_version=ruleset_version
    )
    st = stats_map.get(bp.id) or {}
    matches = int(st.get("matches") or 0)
    wins = int(st.get("wins") or 0)
    losses = int(st.get("losses") or 0)
    draws = int(st.get("draws") or 0)
    elo_sum = int(st.get("elo_sum") or 0)
    last_played_at = st.get("last_played_at")
    avg_elo = (elo_sum / matches) if matches > 0 else 0.0
    winrate = ((wins + 0.5 * draws) / matches) if matches > 0 else 0.0

    u = db.get(User, bp.user_id)
    return GalleryBlueprintRowOut(
        blueprint_id=bp.id,
        name=bp.name,
        mode=bp.mode,  # type: ignore[arg-type]
        ruleset_version=bp.ruleset_version,
        spec_hash=bp.spec_hash,
        submitted_at=_as_aware(bp.submitted_at),
        build_code=bp.build_code or _compute_build_code(bp),
        forked_from_id=bp.forked_from_id,
        creator=GalleryUserOut(
            user_id=bp.user_id,
            display_name=u.display_name if u else "Lab_Unknown",
        ),
        synergy_tags=tags,
        stats=GalleryStatsOut(
            matches=matches,
            wins=wins,
            losses=losses,
            draws=draws,
            winrate=float(winrate),
            avg_elo_delta=float(avg_elo),
            last_played_at=last_played_at,
        ),
    )


@router.get("/blueprints", response_model=list[GalleryBlueprintRowOut])
def list_gallery_blueprints(
    mode: Literal["1v1", "team"] = "1v1",
    tag: str | None = None,
    sort: Literal["recent", "winrate", "trending"] = "trending",
    limit: int = Query(default=30, ge=1, le=100),
    _cursor: str | None = None,
    _viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> list[GalleryBlueprintRowOut]:
    settings = Settings()
    ruleset_version = settings.ruleset_version
    hidden_build_ids = db.scalars(
        select(ModerationHide.target_id).where(ModerationHide.target_type == "build")
    ).all()

    # Simple and robust for small demo DB: fetch submitted (non-bot) and keep latest per user.
    bps = db.scalars(
        select(Blueprint)
        .where(Blueprint.status == "submitted")
        .where(Blueprint.mode == mode)
        .where(Blueprint.ruleset_version == ruleset_version)
        .where(~Blueprint.user_id.like("bot_%"))
        .order_by(
            desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id.asc()
        )
        .limit(500)
    ).all()

    latest_by_user: dict[str, Blueprint] = {}
    for bp in bps:
        if hidden_build_ids and bp.id in hidden_build_ids:
            continue
        if bp.user_id in latest_by_user:
            continue
        latest_by_user[bp.user_id] = bp

    candidates = list(latest_by_user.values())

    # Compute synergy tags + optional filter.
    spec_by_id: dict[str, BlueprintSpec] = {}
    synergy_by_id: dict[str, list[str]] = {}
    filtered: list[Blueprint] = []
    for bp in candidates:
        try:
            spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
        except Exception:  # noqa: BLE001
            continue
        tags = _extract_synergy_tags(spec)
        spec_by_id[bp.id] = spec
        synergy_by_id[bp.id] = tags
        if tag and tag not in tags:
            continue
        filtered.append(bp)

    stats_map = _stats_for_blueprints(
        db,
        blueprint_ids=[b.id for b in filtered],
        mode=mode,
        ruleset_version=ruleset_version,
    )

    user_ids = sorted({b.user_id for b in filtered})
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    user_by_id = {u.id: u for u in users}

    rows: list[GalleryBlueprintRowOut] = []
    for bp in filtered:
        st = stats_map.get(bp.id) or {}
        matches = int(st.get("matches") or 0)
        wins = int(st.get("wins") or 0)
        losses = int(st.get("losses") or 0)
        draws = int(st.get("draws") or 0)
        elo_sum = int(st.get("elo_sum") or 0)
        last_played_at = st.get("last_played_at")
        avg_elo = (elo_sum / matches) if matches > 0 else 0.0
        winrate = ((wins + 0.5 * draws) / matches) if matches > 0 else 0.0

        u = user_by_id.get(bp.user_id)
        rows.append(
            GalleryBlueprintRowOut(
                blueprint_id=bp.id,
                name=bp.name,
                mode=bp.mode,  # type: ignore[arg-type]
                ruleset_version=bp.ruleset_version,
                spec_hash=bp.spec_hash,
                submitted_at=_as_aware(bp.submitted_at),
                build_code=bp.build_code or _compute_build_code(bp),
                forked_from_id=bp.forked_from_id,
                creator=GalleryUserOut(
                    user_id=bp.user_id,
                    display_name=u.display_name if u else "Lab_Unknown",
                ),
                synergy_tags=synergy_by_id.get(bp.id, []),
                stats=GalleryStatsOut(
                    matches=matches,
                    wins=wins,
                    losses=losses,
                    draws=draws,
                    winrate=float(winrate),
                    avg_elo_delta=float(avg_elo),
                    last_played_at=last_played_at,
                ),
            )
        )

    def trending_key(r: GalleryBlueprintRowOut) -> tuple:
        return (
            -(r.stats.matches),
            -(r.stats.winrate),
            r.blueprint_id,
        )

    def winrate_key(r: GalleryBlueprintRowOut) -> tuple:
        return (
            -(r.stats.winrate),
            -(r.stats.matches),
            r.blueprint_id,
        )

    def recent_key(r: GalleryBlueprintRowOut) -> tuple:
        ts = r.submitted_at or datetime.fromtimestamp(0, tz=UTC)
        return (-ts.timestamp(), r.blueprint_id)

    if sort == "recent":
        rows.sort(key=recent_key)
    elif sort == "winrate":
        rows.sort(key=winrate_key)
    else:
        rows.sort(key=trending_key)

    return rows[: int(limit)]


class BuildOfDayOut(BaseModel):
    date: str
    mode: Literal["1v1", "team"]
    blueprint: GalleryBlueprintRowOut | None = None
    source: Literal["override", "auto", "none"] = "none"
    override_blueprint_id: str | None = None
    auto_blueprint_id: str | None = None


@router.get("/build_of_day", response_model=BuildOfDayOut)
def build_of_day(
    mode: Literal["1v1", "team"] = "1v1",
    _viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BuildOfDayOut:
    settings = Settings()
    date_key = kst_date_key()
    overrides = load_build_of_day_overrides()
    resolved = resolve_build_of_day(
        db,
        date_key=date_key,
        mode=mode,  # type: ignore[arg-type]
        ruleset_version=settings.ruleset_version,
        overrides=overrides,
    )
    picked: GalleryBlueprintRowOut | None = None
    if resolved.picked_blueprint_id:
        picked = _gallery_row_for_blueprint_id(
            db,
            blueprint_id=resolved.picked_blueprint_id,
            mode=mode,
            ruleset_version=settings.ruleset_version,
        )

    return BuildOfDayOut(
        date=date_key,
        mode=mode,
        blueprint=picked,
        source=resolved.source,
        override_blueprint_id=resolved.override_blueprint_id,
        auto_blueprint_id=resolved.auto_blueprint_id,
    )
