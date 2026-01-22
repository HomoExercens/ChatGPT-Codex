from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import Blueprint, Match, Rating, User
from neuroleague_api.ray_runtime import ensure_ray
from neuroleague_api.ray_tasks import ranked_match_job
from neuroleague_sim.modifiers import AUGMENTS, select_match_modifiers
from neuroleague_sim.models import BlueprintSpec

router = APIRouter(prefix="/api/tournament", tags=["tournament"])


def _iso_week_id(dt: datetime) -> str:
    year, week, _weekday = dt.isocalendar()
    return f"{int(year)}W{int(week):02d}"


class QueueRequest(BaseModel):
    blueprint_id: str
    seed_set_count: int = Field(default=3, ge=1, le=9)


class QueueResponse(BaseModel):
    match_id: str
    status: Literal["queued", "running"]
    progress: int = Field(default=0, ge=0, le=100)


def _get_or_create_rating(db: Session, user_id: str, mode: str) -> Rating:
    rating = db.get(Rating, {"user_id": user_id, "mode": mode})
    if rating:
        return rating
    rating = Rating(
        user_id=user_id,
        mode=mode,
        elo=1000,
        games_played=0,
        updated_at=datetime.now(UTC),
    )
    db.add(rating)
    db.commit()
    return rating


@router.post("/queue", response_model=QueueResponse)
def queue_tournament(
    request: Request,
    req: QueueRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> QueueResponse:
    player_bp = db.get(Blueprint, req.blueprint_id)
    if not player_bp or player_bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    if player_bp.status != "submitted":
        raise HTTPException(
            status_code=400, detail="Blueprint must be submitted for tournament"
        )

    now = datetime.now(UTC)
    week_id = _iso_week_id(now)

    from neuroleague_api.routers.meta import weekly as weekly_theme
    from neuroleague_api.routers.matches import (
        _pick_bot_blueprint,
        _pick_human_opponent_blueprint,
    )

    theme = weekly_theme(week_id=week_id)
    rules = theme.get("tournament_rules") or {}
    if isinstance(rules, dict) and not bool(rules.get("queue_open", True)):
        raise HTTPException(status_code=503, detail="Tournament queue is closed")

    settings = Settings()
    match_id = f"m_{uuid4().hex}"

    player_rating = _get_or_create_rating(db, user_id, player_bp.mode)
    try:
        opp_bp, _ = _pick_human_opponent_blueprint(
            db,
            mode=player_bp.mode,
            ruleset_version=settings.ruleset_version,
            match_id=match_id,
            player_user_id=user_id,
            player_elo=int(player_rating.elo),
        )
    except Exception:  # noqa: BLE001
        opp_bp = _pick_bot_blueprint(db, mode=player_bp.mode, match_id=match_id)

    spec_a_dict = orjson.loads(player_bp.spec_json)
    spec_b_dict = orjson.loads(opp_bp.spec_json)
    BlueprintSpec.model_validate(spec_a_dict)
    BlueprintSpec.model_validate(spec_b_dict)

    match = Match(
        id=match_id,
        queue_type="tournament",
        week_id=week_id,
        mode=player_bp.mode,
        ruleset_version=settings.ruleset_version,
        portal_id=None,
        augments_a_json="[]",
        augments_b_json="[]",
        seed_set_count=req.seed_set_count,
        user_a_id=user_id,
        user_b_id=opp_bp.user_id,
        blueprint_a_id=player_bp.id,
        blueprint_b_id=opp_bp.id,
        status="queued",
        progress=0,
        ray_job_id=None,
        error_message=None,
        result="pending",
        elo_delta_a=0,
        elo_delta_b=0,
        created_at=now,
        finished_at=None,
    )
    db.add(match)
    db.commit()

    portal_ids = [
        str(p.get("id"))
        for p in (theme.get("featured_portals") or [])
        if isinstance(p, dict) and p.get("id")
    ]
    augment_ids_by_tier: dict[int, list[str]] = {1: [], 2: [], 3: []}
    for a in theme.get("featured_augments") or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        aid = str(a["id"])
        adef = AUGMENTS.get(aid)
        if not adef:
            continue
        augment_ids_by_tier.setdefault(int(adef.tier), []).append(aid)
    for tier in list(augment_ids_by_tier.keys()):
        augment_ids_by_tier[tier] = sorted(set(augment_ids_by_tier[tier]))

    try:
        mods = select_match_modifiers(
            match_id,
            portal_ids=portal_ids or None,
            augment_ids_by_tier=augment_ids_by_tier or None,
        )
        match.portal_id = str(mods.get("portal_id") or "")
        match.augments_a_json = orjson.dumps(mods.get("augments_a") or []).decode(
            "utf-8"
        )
        match.augments_b_json = orjson.dumps(mods.get("augments_b") or []).decode(
            "utf-8"
        )
        db.add(match)
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    ensure_ray()
    obj_ref = ranked_match_job.remote(
        match_id=match_id,
        seed_set_count=req.seed_set_count,
        blueprint_a=spec_a_dict,
        blueprint_b=spec_b_dict,
        user_a_id=user_id,
        user_b_id=opp_bp.user_id,
        mode=player_bp.mode,
        ruleset_version=settings.ruleset_version,
        db_url=settings.db_url,
        artifacts_dir=settings.artifacts_dir,
        queue_type="tournament",
        update_ratings=False,
    )
    match.ray_job_id = obj_ref.hex()
    db.add(match)
    db.commit()

    try:
        opp_type: Literal["human", "bot"] = (
            "bot" if (opp_bp.user_id or "").startswith("bot_") else "human"
        )
        log_event(
            db,
            type="tournament_queue",
            user_id=user_id,
            request=request,
            payload={
                "match_id": match_id,
                "mode": str(player_bp.mode),
                "week_id": str(week_id),
                "blueprint_id": str(player_bp.id),
                "opponent_type": opp_type,
                "opponent_user_id": str(opp_bp.user_id or ""),
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    return QueueResponse(match_id=match_id, status="queued", progress=0)


class TournamentRow(BaseModel):
    rank: int
    user_id: str
    display_name: str
    points: int
    matches_counted: int
    wins: int
    losses: int
    draws: int


def _points_for_match(result: str) -> int:
    if result == "A":
        return 3
    if result == "draw":
        return 1
    return 0


def _tournament_table(
    db: Session, *, week_id: str, mode: str, matches_counted: int
) -> list[dict[str, Any]]:
    matches = db.scalars(
        select(Match)
        .where(Match.queue_type == "tournament")
        .where(Match.week_id == week_id)
        .where(Match.mode == mode)
        .where(Match.status == "done")
        .order_by(Match.created_at.asc(), Match.id.asc())
    ).all()

    by_user: dict[str, list[Match]] = {}
    for m in matches:
        if not m.user_a_id:
            continue
        by_user.setdefault(m.user_a_id, []).append(m)

    rows: list[dict[str, Any]] = []
    for uid, ms in by_user.items():
        ms_sorted = sorted(ms, key=lambda m: (m.created_at, m.id))
        counted = ms_sorted[: int(matches_counted)]
        wins = sum(1 for m in counted if m.result == "A")
        losses = sum(1 for m in counted if m.result == "B")
        draws = sum(1 for m in counted if m.result == "draw")
        points = sum(_points_for_match(m.result) for m in counted)
        rows.append(
            {
                "user_id": uid,
                "points": int(points),
                "matches_counted": len(counted),
                "wins": int(wins),
                "losses": int(losses),
                "draws": int(draws),
            }
        )

    rows.sort(
        key=lambda r: (-r["points"], -r["wins"], -r["matches_counted"], r["user_id"])
    )
    return rows


@router.get("/leaderboard", response_model=list[TournamentRow])
def leaderboard(
    week_id: str | None = None,
    mode: Literal["1v1", "team"] = "team",
    limit: int = Query(default=50, ge=1, le=100),
    _viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> list[TournamentRow]:
    from neuroleague_api.routers.meta import weekly as weekly_theme

    now = datetime.now(UTC)
    wid = week_id or _iso_week_id(now)
    theme = weekly_theme(week_id=wid)
    rules = theme.get("tournament_rules") or {}
    matches_counted = (
        int(rules.get("matches_counted") or 10) if isinstance(rules, dict) else 10
    )

    table = _tournament_table(
        db, week_id=wid, mode=mode, matches_counted=matches_counted
    )
    user_ids = [r["user_id"] for r in table[: int(limit)]]
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    user_by_id = {u.id: u for u in users}

    out: list[TournamentRow] = []
    for idx, row in enumerate(table[: int(limit)], start=1):
        u = user_by_id.get(row["user_id"])
        out.append(
            TournamentRow(
                rank=idx,
                user_id=row["user_id"],
                display_name=u.display_name if u else "Lab_Unknown",
                points=int(row["points"]),
                matches_counted=int(row["matches_counted"]),
                wins=int(row["wins"]),
                losses=int(row["losses"]),
                draws=int(row["draws"]),
            )
        )
    return out


class TournamentMeOut(BaseModel):
    week_id: str
    mode: Literal["1v1", "team"]
    matches_counted_limit: int
    matches_counted: int
    points: int
    wins: int
    losses: int
    draws: int
    rank: int | None = None


@router.get("/me", response_model=TournamentMeOut)
def me(
    week_id: str | None = None,
    mode: Literal["1v1", "team"] = "team",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> TournamentMeOut:
    from neuroleague_api.routers.meta import weekly as weekly_theme

    now = datetime.now(UTC)
    wid = week_id or _iso_week_id(now)
    theme = weekly_theme(week_id=wid)
    rules = theme.get("tournament_rules") or {}
    matches_counted = (
        int(rules.get("matches_counted") or 10) if isinstance(rules, dict) else 10
    )

    table = _tournament_table(
        db, week_id=wid, mode=mode, matches_counted=matches_counted
    )
    rank = None
    row = next((r for r in table if r["user_id"] == user_id), None)
    if row is None:
        return TournamentMeOut(
            week_id=wid,
            mode=mode,
            matches_counted_limit=matches_counted,
            matches_counted=0,
            points=0,
            wins=0,
            losses=0,
            draws=0,
            rank=None,
        )

    for idx, r in enumerate(table, start=1):
        if r["user_id"] == user_id:
            rank = idx
            break

    return TournamentMeOut(
        week_id=wid,
        mode=mode,
        matches_counted_limit=matches_counted,
        matches_counted=int(row["matches_counted"]),
        points=int(row["points"]),
        wins=int(row["wins"]),
        losses=int(row["losses"]),
        draws=int(row["draws"]),
        rank=rank,
    )
