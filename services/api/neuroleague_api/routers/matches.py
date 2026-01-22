from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import os
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import (
    Blueprint,
    Event,
    Match,
    Rating,
    Replay,
    RenderJob,
    User,
)
from neuroleague_api.rate_limit import check_rate_limit_dual
from neuroleague_api.match_sync import run_match_sync
from neuroleague_api.storage import ensure_artifacts_dir, load_replay_json
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.modifiers import select_match_modifiers

router = APIRouter(prefix="/api/matches", tags=["matches"])


class QueueRequest(BaseModel):
    blueprint_id: str
    seed_set_count: int = Field(default=3, ge=1, le=9)
    lenv: str | None = Field(default=None, max_length=16)
    cv: str | None = Field(default=None, max_length=32)
    ctpl: str | None = Field(default=None, max_length=64)


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


def _pick_bot_blueprint(db: Session, *, mode: str, match_id: str) -> Blueprint:
    bots = db.scalars(
        select(Blueprint)
        .where(Blueprint.user_id.like("bot_%"))
        .where(Blueprint.mode == mode)
        .order_by(Blueprint.id)
    ).all()
    if not bots:
        raise HTTPException(status_code=500, detail="No bot blueprints seeded")
    digest = hashlib.sha256(match_id.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "little", signed=False) % len(bots)
    return bots[idx]


def _recent_opponents(
    db: Session,
    *,
    player_user_id: str,
    mode: str,
    window: int,
) -> list[str]:
    if window <= 0:
        return []
    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == player_user_id)
        .where(Match.mode == mode)
        .where(Match.status != "failed")
        .order_by(desc(Match.created_at))
        .limit(int(window))
    ).all()
    return [m.user_b_id for m in matches if m.user_b_id]


def _repeat_penalty(
    *,
    opponent_user_id: str,
    recent_opponents: list[str],
    window_penalty: int,
    recent_window: int,
    recent_penalty: int,
) -> int:
    if not opponent_user_id:
        return 0
    count_window = recent_opponents.count(opponent_user_id)
    count_recent = recent_opponents[: max(0, int(recent_window))].count(
        opponent_user_id
    )
    return int(window_penalty) * count_window + int(recent_penalty) * count_recent


def _pick_human_opponent_blueprint(
    db: Session,
    *,
    mode: str,
    ruleset_version: str,
    match_id: str,
    player_user_id: str,
    player_elo: int,
) -> tuple[Blueprint, int]:
    settings = Settings()
    recent = _recent_opponents(
        db,
        player_user_id=player_user_id,
        mode=mode,
        window=int(settings.matchmaking_repeat_window),
    )
    bps = db.scalars(
        select(Blueprint)
        .where(Blueprint.status == "submitted")
        .where(Blueprint.mode == mode)
        .where(Blueprint.ruleset_version == ruleset_version)
        .where(Blueprint.user_id != player_user_id)
        .where(~Blueprint.user_id.like("bot_%"))
        .order_by(
            desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id
        )
    ).all()

    latest_by_user: dict[str, Blueprint] = {}
    for bp in bps:
        if bp.user_id in latest_by_user:
            continue
        latest_by_user[bp.user_id] = bp

    if not latest_by_user:
        raise ValueError("No human candidates")

    user_ids = list(latest_by_user.keys())
    ratings = db.scalars(
        select(Rating).where(Rating.user_id.in_(user_ids)).where(Rating.mode == mode)
    ).all()
    rating_by_user = {r.user_id: int(r.elo) for r in ratings}

    scored: list[tuple[int, int, str, int, Blueprint]] = []
    for uid, bp in latest_by_user.items():
        elo = rating_by_user.get(uid, 1000)
        elo_diff = abs(int(elo) - int(player_elo))
        penalty = _repeat_penalty(
            opponent_user_id=uid,
            recent_opponents=recent,
            window_penalty=int(settings.matchmaking_repeat_penalty),
            recent_window=int(settings.matchmaking_repeat_recent_window),
            recent_penalty=int(settings.matchmaking_repeat_recent_penalty),
        )
        total_score = int(elo_diff) + int(penalty)
        scored.append((total_score, int(elo_diff), uid, int(elo), bp))

    scored.sort(key=lambda row: (row[0], row[2]))
    best_score = scored[0][0]
    margin = max(0, int(settings.matchmaking_pick_margin))
    pool = [row for row in scored if row[0] <= best_score + margin]
    pool = pool[: min(10, len(pool))]
    digest = hashlib.sha256(match_id.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "little", signed=False) % len(pool)
    _, _, _, opp_elo, opp_bp = pool[idx]
    return opp_bp, opp_elo


def _maybe_refresh_ray_status(db: Session, match: Match) -> None:
    if match.status not in ("queued", "running"):
        return
    if not match.ray_job_id:
        return
    try:
        from neuroleague_api.ray_runtime import ensure_ray
        import ray  # type: ignore
    except Exception:  # noqa: BLE001
        return

    ensure_ray()

    raw = match.ray_job_id.strip()
    if raw.startswith("ObjectRef(") and raw.endswith(")"):
        raw = raw[len("ObjectRef(") : -1]
    try:
        obj_ref = ray.ObjectRef.from_hex(raw)
    except Exception:  # noqa: BLE001
        return

    ready, _ = ray.wait([obj_ref], timeout=0)
    if not ready:
        return

    try:
        ray.get(obj_ref)
    except Exception as exc:  # noqa: BLE001
        now = datetime.now(UTC)
        match.status = "failed"
        match.error_message = str(exc)
        match.finished_at = now
        db.add(match)
        db.commit()
    else:
        try:
            db.refresh(match)
        except Exception:  # noqa: BLE001
            pass


def _matchmaking_reason(
    *,
    queue_type: str,
    opponent_type: Literal["human", "bot"],
) -> str | None:
    if queue_type not in ("ranked", "tournament"):
        return None
    if opponent_type == "bot":
        return "pool low, bot fallback"
    return "similar Elo, different user"


@router.post("/queue", response_model=QueueResponse)
def queue_ranked(
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
            status_code=400, detail="Blueprint must be submitted for ranked"
        )

    settings = Settings()
    if settings.desktop_mode:
        raise HTTPException(status_code=503, detail="ranked_queue_disabled_desktop_mode")
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="ranked_queue",
        per_minute_user=int(settings.rate_limit_ranked_queue_per_minute),
        per_hour_user=int(settings.rate_limit_ranked_queue_per_hour),
        per_minute_ip=int(settings.rate_limit_ranked_queue_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_ranked_queue_per_hour_ip),
        extra_detail={"mode": str(player_bp.mode or "")},
    )

    match_id = f"m_{uuid4().hex}"
    now = datetime.now(UTC)

    queued_before = int(
        db.scalar(
            select(func.count(Match.id))
            .where(Match.user_a_id == user_id)
            .where(Match.queue_type == "ranked")
        )
        or 0
    )
    is_first_match = queued_before == 0

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

    recent = _recent_opponents(
        db,
        player_user_id=user_id,
        mode=player_bp.mode,
        window=int(settings.matchmaking_repeat_window),
    )
    if opp_bp.user_id and not opp_bp.user_id.startswith("bot_"):
        count_window = recent.count(opp_bp.user_id)
        if count_window >= 2:
            db.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=user_id,
                    type="anti_abuse_flag",
                    payload_json=orjson.dumps(
                        {
                            "user_id": user_id,
                            "mode": player_bp.mode,
                            "reason": "repeat_opponent",
                            "opponent_id": opp_bp.user_id,
                            "window": int(settings.matchmaking_repeat_window),
                            "count": int(count_window) + 1,
                            "match_id": match_id,
                        }
                    ).decode("utf-8"),
                    created_at=now,
                )
            )
        if recent and recent[0] == opp_bp.user_id:
            db.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=user_id,
                    type="anti_abuse_flag",
                    payload_json=orjson.dumps(
                        {
                            "user_id": user_id,
                            "mode": player_bp.mode,
                            "reason": "repeat_opponent_consecutive",
                            "opponent_id": opp_bp.user_id,
                            "match_id": match_id,
                        }
                    ).decode("utf-8"),
                    created_at=now,
                )
            )

    spec_a_dict = orjson.loads(player_bp.spec_json)
    spec_b_dict = orjson.loads(opp_bp.spec_json)
    BlueprintSpec.model_validate(spec_a_dict)
    BlueprintSpec.model_validate(spec_b_dict)

    match = Match(
        id=match_id,
        queue_type="ranked",
        week_id=None,
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

    try:
        mods = select_match_modifiers(match_id)
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

    try:
        opp_type: Literal["human", "bot"] = (
            "bot" if (opp_bp.user_id or "").startswith("bot_") else "human"
        )
        variants: dict[str, str] = {}
        if req.lenv:
            variants["clip_len_v1"] = str(req.lenv)[:16]
        if req.ctpl:
            variants["captions_v2"] = str(req.ctpl)[:64]
        log_event(
            db,
            type="ranked_queue",
            user_id=user_id,
            request=request,
            payload={
                "match_id": match_id,
                "mode": str(player_bp.mode),
                "blueprint_id": str(player_bp.id),
                "opponent_type": opp_type,
                "opponent_user_id": str(opp_bp.user_id or ""),
                "matchmaking_reason": _matchmaking_reason(
                    queue_type="ranked", opponent_type=opp_type
                ),
                "variants": variants,
                "captions_version": str(req.cv)[:32] if req.cv else None,
            },
        )
        if is_first_match:
            log_event(
                db,
                type="first_match_queued",
                user_id=user_id,
                request=request,
                payload={
                    "match_id": match_id,
                    "queue_type": "ranked",
                    "mode": str(player_bp.mode),
                },
            )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    from neuroleague_api.ray_runtime import ensure_ray
    from neuroleague_api.ray_tasks import ranked_match_job

    if os.environ.get("NEUROLEAGUE_E2E_FAST") == "1":
        try:
            run_match_sync(
                db=db,
                match=match,
                blueprint_a=spec_a_dict,
                blueprint_b=spec_b_dict,
                user_a_id=str(user_id),
                user_b_id=str(opp_bp.user_id),
                mode=str(player_bp.mode),
                ruleset_version=str(settings.ruleset_version),
                seed_set_count=int(req.seed_set_count),
                queue_type="ranked",
                update_ratings=True,
            )
        except Exception as exc:  # noqa: BLE001
            now = datetime.now(UTC)
            match.status = "failed"
            match.error_message = str(exc)[:800]
            match.finished_at = now
            db.add(match)
            db.commit()
    else:
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
        )
        match.ray_job_id = obj_ref.hex()
        db.add(match)
        db.commit()

    return QueueResponse(match_id=match_id, status="queued", progress=0)


class MatchRow(BaseModel):
    id: str
    queue_type: str
    week_id: str | None = None
    mode: str
    portal_id: str | None = None
    augments_a: list[dict[str, Any]] = Field(default_factory=list)
    augments_b: list[dict[str, Any]] = Field(default_factory=list)
    opponent: str
    opponent_type: Literal["human", "bot"]
    opponent_elo: int | None = None
    matchmaking_reason: str | None = None
    status: str
    progress: int
    result: Literal["win", "loss", "draw"] | None
    elo_change: int
    error_message: str | None = None
    created_at: datetime


@router.get("", response_model=list[MatchRow])
def list_matches(
    mode: Literal["1v1", "team"] | None = None,
    queue_type: Literal["ranked", "tournament", "all"] = "ranked",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> list[MatchRow]:
    q = select(Match).where(Match.user_a_id == user_id)
    if mode:
        q = q.where(Match.mode == mode)
    if queue_type != "all":
        q = q.where(Match.queue_type == queue_type)
    matches = db.scalars(q.order_by(desc(Match.created_at)).limit(50)).all()
    out: list[MatchRow] = []
    for m in matches:
        _maybe_refresh_ray_status(db, m)
        opp_user = db.get(User, m.user_b_id) if m.user_b_id else None
        opp = opp_user.display_name if opp_user else "Lab_Unknown"
        opp_type: Literal["human", "bot"] = (
            "bot" if (m.user_b_id or "").startswith("bot_") else "human"
        )
        m_queue_type = getattr(m, "queue_type", "ranked")
        opp_elo: int | None = None
        if opp_type == "human" and m.user_b_id:
            opp_rating = db.get(Rating, {"user_id": m.user_b_id, "mode": m.mode})
            opp_elo = int(opp_rating.elo) if opp_rating else 1000
        result: Literal["win", "loss", "draw"] | None = None
        if m.status == "done":
            result = "win" if m.result == "A" else "loss" if m.result == "B" else "draw"
        aug_a: list[dict[str, Any]] = []
        aug_b: list[dict[str, Any]] = []
        try:
            aug_a = orjson.loads(m.augments_a_json) if m.augments_a_json else []
        except Exception:  # noqa: BLE001
            aug_a = []
        try:
            aug_b = orjson.loads(m.augments_b_json) if m.augments_b_json else []
        except Exception:  # noqa: BLE001
            aug_b = []

        out.append(
            MatchRow(
                id=m.id,
                queue_type=m_queue_type,
                week_id=getattr(m, "week_id", None),
                mode=m.mode,
                portal_id=m.portal_id,
                augments_a=aug_a if isinstance(aug_a, list) else [],
                augments_b=aug_b if isinstance(aug_b, list) else [],
                opponent=opp,
                opponent_type=opp_type,
                opponent_elo=opp_elo,
                matchmaking_reason=_matchmaking_reason(
                    queue_type=str(m_queue_type), opponent_type=opp_type
                ),
                status=m.status,
                progress=int(m.progress or 0),
                result=result,
                elo_change=int(m.elo_delta_a or 0),
                error_message=m.error_message,
                created_at=m.created_at,
            )
        )
    return out


class MatchDetail(BaseModel):
    id: str
    queue_type: str
    week_id: str | None = None
    mode: str
    ruleset_version: str
    portal_id: str | None = None
    augments_a: list[dict[str, Any]] = Field(default_factory=list)
    augments_b: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    progress: int
    result: str
    user_a: str
    user_b: str
    opponent_display_name: str
    opponent_type: Literal["human", "bot"]
    opponent_elo: int | None = None
    matchmaking_reason: str | None = None
    blueprint_a_id: str | None
    blueprint_b_id: str | None
    seed_set_count: int
    elo_delta_a: int
    replay_id: str | None
    highlights: list[dict[str, Any]]
    error_message: str | None = None


@router.get("/{match_id}", response_model=MatchDetail)
def match_detail(
    match_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> MatchDetail:
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    if m.user_a_id != user_id and str(m.status or "") != "done":
        raise HTTPException(status_code=404, detail="Match not found")
    _maybe_refresh_ray_status(db, m)
    replay = db.scalar(select(Replay).where(Replay.match_id == match_id))
    payload: dict[str, Any] = {}
    if replay:
        payload = load_replay_json(artifact_path=replay.artifact_path)
    opp_user = db.get(User, m.user_b_id) if m.user_b_id else None
    opp_name = opp_user.display_name if opp_user else "Lab_Unknown"
    opp_type: Literal["human", "bot"] = (
        "bot" if (m.user_b_id or "").startswith("bot_") else "human"
    )
    opp_elo: int | None = None
    if opp_type == "human" and m.user_b_id:
        opp_rating = db.get(Rating, {"user_id": m.user_b_id, "mode": m.mode})
        opp_elo = int(opp_rating.elo) if opp_rating else 1000
    m_queue_type = getattr(m, "queue_type", "ranked")
    aug_a: list[dict[str, Any]] = []
    aug_b: list[dict[str, Any]] = []
    try:
        aug_a = orjson.loads(m.augments_a_json) if m.augments_a_json else []
    except Exception:  # noqa: BLE001
        aug_a = []
    try:
        aug_b = orjson.loads(m.augments_b_json) if m.augments_b_json else []
    except Exception:  # noqa: BLE001
        aug_b = []
    return MatchDetail(
        id=m.id,
        queue_type=m_queue_type,
        week_id=getattr(m, "week_id", None),
        mode=m.mode,
        ruleset_version=m.ruleset_version,
        portal_id=m.portal_id,
        augments_a=aug_a if isinstance(aug_a, list) else [],
        augments_b=aug_b if isinstance(aug_b, list) else [],
        status=m.status,
        progress=int(m.progress or 0),
        result=m.result,
        user_a=m.user_a_id or "unknown",
        user_b=m.user_b_id or "unknown",
        opponent_display_name=opp_name,
        opponent_type=opp_type,
        opponent_elo=opp_elo,
        matchmaking_reason=_matchmaking_reason(
            queue_type=str(m_queue_type), opponent_type=opp_type
        ),
        blueprint_a_id=m.blueprint_a_id,
        blueprint_b_id=m.blueprint_b_id,
        seed_set_count=m.seed_set_count,
        elo_delta_a=m.elo_delta_a,
        replay_id=replay.id if replay else None,
        highlights=payload.get("highlights", []),
        error_message=m.error_message,
    )


@router.get("/{match_id}/replay")
def match_replay(
    request: Request,
    match_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    if m.user_a_id != user_id and str(m.status or "") != "done":
        raise HTTPException(status_code=404, detail="Match not found")
    _maybe_refresh_ray_status(db, m)
    replay = db.scalar(select(Replay).where(Replay.match_id == match_id))
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not ready")
    try:
        seen = db.scalar(
            select(Event.id)
            .where(Event.user_id == user_id)
            .where(Event.type.in_(["replay_open", "first_replay_open"]))
            .limit(1)
        )
        if seen is None:
            log_event(
                db,
                type="first_replay_open",
                user_id=user_id,
                request=request,
                payload={
                    "match_id": match_id,
                    "replay_id": replay.id,
                    "queue_type": str(getattr(m, "queue_type", "ranked")),
                    "mode": str(m.mode or ""),
                },
            )
        log_event(
            db,
            type="replay_open",
            user_id=user_id,
            request=request,
            payload={
                "match_id": match_id,
                "replay_id": replay.id,
                "queue_type": str(getattr(m, "queue_type", "ranked")),
                "mode": str(m.mode or ""),
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass
    return load_replay_json(artifact_path=replay.artifact_path)


@router.get("/{match_id}/highlights")
def match_highlights(
    match_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    m = db.get(Match, match_id)
    if not m or m.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Match not found")
    _maybe_refresh_ray_status(db, m)
    replay = db.scalar(select(Replay).where(Replay.match_id == match_id))
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not ready")
    payload = load_replay_json(artifact_path=replay.artifact_path)
    return {"highlights": payload.get("highlights", [])}


class BestClipAsset(BaseModel):
    kind: Literal["thumbnail", "vertical_mp4"]
    cache_key: str
    status: Literal["missing", "queued", "running", "done", "failed"]
    job_id: str | None = None
    artifact_url: str | None = None
    error_message: str | None = None


class BestClipOut(BaseModel):
    match_id: str
    replay_id: str
    start_tick: int
    end_tick: int
    start_sec: float
    end_sec: float
    title: str
    summary: str
    share_url: str
    share_url_vertical: str
    assets: list[BestClipAsset]


@router.get("/{match_id}/best_clip", response_model=BestClipOut)
def best_clip(
    match_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BestClipOut:
    from neuroleague_api.clip_render import (
        CAPTIONS_VERSION,
        best_clip_segment,
        captions_plan_for_segment,
        cache_key,
    )
    from neuroleague_api.storage_backend import get_storage_backend

    m = db.get(Match, match_id)
    if not m or m.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Match not found")
    _maybe_refresh_ray_status(db, m)
    replay = db.scalar(select(Replay).where(Replay.match_id == match_id))
    if not replay:
        raise HTTPException(status_code=409, detail="Replay not ready")

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    if not digest:
        raise HTTPException(status_code=500, detail="Replay digest missing")

    highlights = payload.get("highlights") if isinstance(payload, dict) else None
    top: dict[str, Any] = {}
    if isinstance(highlights, list) and highlights:
        for h in highlights:
            if isinstance(h, dict):
                top = h
                break
    start_tick, end_tick = best_clip_segment(payload, max_duration_sec=12.0)
    captions_plan = captions_plan_for_segment(
        replay_payload=payload, start_tick=start_tick, end_tick=end_tick
    )

    start_sec = start_tick / 20.0
    end_sec = end_tick / 20.0
    title = str(top.get("title") or "Turning Point")
    summary = str(top.get("summary") or "")

    thumb_key = cache_key(
        replay_digest=digest,
        kind="thumbnail",
        start_tick=start_tick,
        end_tick=end_tick,
        fps=1,
        scale=1,
        theme="dark",
    )
    mp4_key = cache_key(
        replay_digest=digest,
        kind="clip_mp4",
        start_tick=start_tick,
        end_tick=end_tick,
        fps=12,
        scale=1,
        theme="dark",
        aspect="9:16",
        captions_version=captions_plan.version or CAPTIONS_VERSION,
        captions_template_id=captions_plan.template_id,
    )
    thumb_asset_key = f"clips/thumbnails/thumb_{replay.id}_{thumb_key[:16]}.png"
    mp4_asset_key = f"clips/mp4/clip_mp4_{replay.id}_{mp4_key[:16]}.mp4"
    backend = get_storage_backend()

    def _safe_exists(key: str) -> bool:
        try:
            return bool(backend.exists(key=key))
        except Exception:  # noqa: BLE001
            return False

    def _asset(
        kind: Literal["thumbnail", "vertical_mp4"],
        *,
        cache_key: str,
        asset_key: str,
        exists: bool,
    ) -> BestClipAsset:
        if exists:
            return BestClipAsset(
                kind=kind,
                cache_key=cache_key,
                status="done",
                job_id=None,
                artifact_url=backend.public_url(key=asset_key),
            )
        existing = db.scalar(
            select(RenderJob)
            .where(RenderJob.user_id == user_id)
            .where(RenderJob.cache_key == cache_key)
            .order_by(RenderJob.created_at.desc())
            .limit(1)
        )
        if not existing:
            return BestClipAsset(
                kind=kind,
                cache_key=cache_key,
                status="missing",
                job_id=None,
                artifact_url=None,
            )
        return BestClipAsset(
            kind=kind,
            cache_key=cache_key,
            status=existing.status
            if existing.status in ("queued", "running", "done", "failed")
            else "missing",
            job_id=existing.id,
            artifact_url=None,
            error_message=existing.error_message,
        )

    q = f"start={start_sec:.1f}&end={end_sec:.1f}"
    share_url = f"/s/clip/{replay.id}?{q}"
    share_url_vertical = f"/s/clip/{replay.id}?{q}&v=1"

    return BestClipOut(
        match_id=match_id,
        replay_id=replay.id,
        start_tick=start_tick,
        end_tick=end_tick,
        start_sec=start_sec,
        end_sec=end_sec,
        title=title,
        summary=summary,
        share_url=share_url,
        share_url_vertical=share_url_vertical,
        assets=[
            _asset(
                "thumbnail",
                cache_key=thumb_key,
                asset_key=thumb_asset_key,
                exists=_safe_exists(thumb_asset_key),
            ),
            _asset(
                "vertical_mp4",
                cache_key=mp4_key,
                asset_key=mp4_asset_key,
                exists=_safe_exists(mp4_asset_key),
            ),
        ],
    )


class BestClipJobsOut(BaseModel):
    thumbnail: dict[str, Any]
    vertical_mp4: dict[str, Any]


@router.post("/{match_id}/best_clip_jobs", response_model=BestClipJobsOut)
def create_best_clip_jobs(
    request: Request,
    match_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BestClipJobsOut:
    m = db.get(Match, match_id)
    if not m or m.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Match not found")
    replay = db.scalar(select(Replay).where(Replay.match_id == match_id))
    if not replay:
        raise HTTPException(status_code=409, detail="Replay not ready")

    payload = load_replay_json(artifact_path=replay.artifact_path)
    from neuroleague_api.clip_render import best_clip_segment

    start_tick, end_tick = best_clip_segment(payload, max_duration_sec=12.0)
    # Share URLs use 0.1s resolution; align best-clip render jobs to the same
    # quantized range so /s/clip/* (mp4 + kit.zip) hits the same cache key.
    start_t = float(f"{(float(start_tick) / 20.0):.1f}")
    end_t = float(f"{(float(end_tick) / 20.0):.1f}")

    from neuroleague_api.routers.replays import (
        ClipJobRequest,
        ThumbnailJobRequest,
        create_clip_job,
        create_thumbnail_job,
    )

    thumb = create_thumbnail_job(
        replay_id=replay.id,
        request=request,
        req=ThumbnailJobRequest(start=start_t, end=end_t, scale=1, theme="dark"),
        user_id=user_id,
        db=db,
    )
    vertical = create_clip_job(
        replay_id=replay.id,
        request=request,
        req=ClipJobRequest(
            start=start_t,
            end=end_t,
            format="mp4",
            fps=12,
            scale=1,
            theme="dark",
            aspect="9:16",
            captions=True,
        ),
        user_id=user_id,
        db=db,
    )

    return BestClipJobsOut(
        thumbnail={
            "job_id": thumb.job_id,
            "status": thumb.status,
            "cache_key": thumb.cache_key,
        },
        vertical_mp4={
            "job_id": vertical.job_id,
            "status": vertical.status,
            "cache_key": vertical.cache_key,
        },
    )


class SharecardJobRequest(BaseModel):
    theme: Literal["dark", "light"] = "dark"
    locale: Literal["en", "ko"] = "en"


@router.post("/{match_id}/sharecard_jobs")
def create_sharecard_job(
    request: Request,
    match_id: str,
    req: SharecardJobRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    from neuroleague_api.moderation import ensure_not_soft_banned

    m = db.get(Match, match_id)
    if not m or m.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Match not found")
    replay = db.scalar(select(Replay).where(Replay.match_id == match_id))
    if not replay:
        raise HTTPException(status_code=409, detail="Replay not ready")

    ensure_not_soft_banned(db, user_id=user_id)

    digest = str(replay.digest or "")
    if not digest:
        payload = load_replay_json(artifact_path=replay.artifact_path)
        digest = str(payload.get("digest") or "")
    if not digest:
        raise HTTPException(status_code=500, detail="Replay digest missing")
    safe_digest = digest[:12] if digest else "unknown"

    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="render_jobs",
        per_minute_user=int(settings.rate_limit_render_jobs_per_minute),
        per_hour_user=int(settings.rate_limit_render_jobs_per_hour),
        per_minute_ip=int(settings.rate_limit_render_jobs_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_render_jobs_per_hour_ip),
        extra_detail={"kind": "sharecard"},
    )

    root = ensure_artifacts_dir()
    out_dir = root / "sharecards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path_v2 = (
        out_dir / f"sharecard_v2_{replay.id}_{safe_digest}_{req.theme}_{req.locale}.png"
    )
    out_path_v1 = out_dir / f"sharecard_v1_{replay.id}_{safe_digest}.png"

    cache_msg = f"sharecard_v2:{digest}:{req.theme}:{req.locale}"
    cache_key = hashlib.sha256(cache_msg.encode("utf-8")).hexdigest()

    existing = db.scalar(
        select(RenderJob)
        .where(RenderJob.user_id == user_id)
        .where(RenderJob.cache_key == cache_key)
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )
    if existing and existing.status in ("queued", "running", "done"):
        return {
            "job_id": existing.id,
            "status": existing.status,
            "cache_key": cache_key,
        }

    now = datetime.now(UTC)
    if out_path_v2.exists() or out_path_v1.exists():
        chosen = out_path_v2 if out_path_v2.exists() else out_path_v1
        job = RenderJob(
            id=f"rj_{uuid4().hex}",
            user_id=user_id,
            kind="sharecard",
            target_replay_id=replay.id,
            target_match_id=match_id,
            params_json=orjson.dumps({"theme": req.theme, "locale": req.locale}).decode(
                "utf-8"
            ),
            cache_key=cache_key,
            status="done",
            progress=100,
            ray_job_id=None,
            artifact_path=str(chosen),
            error_message=None,
            created_at=now,
            finished_at=now,
        )
        db.add(job)
        db.commit()
        return {"job_id": job.id, "status": job.status, "cache_key": cache_key}

    job = RenderJob(
        id=f"rj_{uuid4().hex}",
        user_id=user_id,
        kind="sharecard",
        target_replay_id=replay.id,
        target_match_id=match_id,
        params_json=orjson.dumps({"theme": req.theme, "locale": req.locale}).decode(
            "utf-8"
        ),
        cache_key=cache_key,
        status="queued",
        progress=0,
        ray_job_id=None,
        artifact_path=None,
        error_message=None,
        created_at=now,
        finished_at=None,
    )
    db.add(job)
    db.commit()

    settings = Settings()
    if os.environ.get("NEUROLEAGUE_E2E_FAST") == "1":
        from neuroleague_api.render_runner import run_render_sharecard_job

        run_render_sharecard_job(
            job_id=job.id,
            replay_id=replay.id,
            theme=req.theme,
            locale=req.locale,
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        try:
            db.refresh(job)
        except Exception:  # noqa: BLE001
            pass
    elif settings.desktop_mode:
        pass
    else:
        from neuroleague_api.ray_runtime import ensure_ray

        ensure_ray()
        from neuroleague_api.ray_tasks import render_sharecard_job

        obj_ref = render_sharecard_job.remote(
            job_id=job.id,
            replay_id=replay.id,
            theme=req.theme,
            locale=req.locale,
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        job.ray_job_id = obj_ref.hex()
        db.add(job)
        db.commit()

    return {"job_id": job.id, "status": job.status, "cache_key": cache_key}
