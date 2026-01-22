from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session
import os

from neuroleague_api.challenges import derive_challenge_match_id
from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.match_sync import run_match_sync
from neuroleague_api.rate_limit import check_rate_limit_dual
from neuroleague_api.ray_runtime import ensure_ray
from neuroleague_api.ray_tasks import ranked_match_job
from neuroleague_api.models import (
    Blueprint,
    Challenge,
    ChallengeAttempt,
    Match,
    Replay,
    User,
)
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.modifiers import select_match_modifiers

router = APIRouter(prefix="/api/challenges", tags=["challenges"])


def _clamp_seconds(
    *, start: float, end: float | None, max_duration: float = 12.0
) -> tuple[float, float | None]:
    s = float(start or 0.0)
    e = float(end) if end is not None else None
    if s < 0:
        s = 0.0
    if e is not None and e < 0:
        e = 0.0
    if e is not None and e < s:
        s, e = e, s
    if e is not None and (e - s) > float(max_duration):
        e = s + float(max_duration)
    return s, e


def _pick_bot_blueprint(db: Session, *, mode: str, seed: str) -> Blueprint:
    bots = db.scalars(
        select(Blueprint)
        .where(Blueprint.user_id.like("bot_%"))
        .where(Blueprint.mode == mode)
        .order_by(Blueprint.id.asc())
    ).all()
    if not bots:
        raise HTTPException(status_code=500, detail="No bot blueprints seeded")
    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "little", signed=False) % len(bots)
    return bots[idx]


def _default_spec(mode: Literal["1v1", "team"], ruleset_version: str) -> dict[str, Any]:
    if mode == "team":
        return {
            "ruleset_version": ruleset_version,
            "mode": "team",
            "team": [
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {"armor": "reinforced_plate"},
                },
                {
                    "creature_id": "iron_striker",
                    "formation": "front",
                    "items": {"weapon": "plasma_lance"},
                },
                {
                    "creature_id": "crystal_weaver",
                    "formation": "back",
                    "items": {"utility": "targeting_array"},
                },
            ],
        }
    return {
        "ruleset_version": ruleset_version,
        "mode": "1v1",
        "team": [{"creature_id": "slime_knight", "formation": "front", "items": {}}],
    }


class ChallengeCreateRequest(BaseModel):
    kind: Literal["build", "clip"]
    target_blueprint_id: str | None = None
    target_replay_id: str | None = None
    start: float = 0.0
    end: float | None = None


class ChallengeCreateResponse(BaseModel):
    challenge_id: str
    share_url: str


@router.post("", response_model=ChallengeCreateResponse)
def create_challenge(
    req: ChallengeCreateRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ChallengeCreateResponse:
    settings = Settings()
    now = datetime.now(UTC)

    target_bp: Blueprint | None = None
    target_replay: Replay | None = None
    target_match: Match | None = None

    if req.kind == "build":
        if not req.target_blueprint_id:
            raise HTTPException(status_code=400, detail="target_blueprint_id required")
        target_bp = db.get(Blueprint, req.target_blueprint_id)
        if not target_bp or target_bp.status != "submitted":
            raise HTTPException(status_code=404, detail="Blueprint not found")
        mode = str(target_bp.mode)
        ruleset = str(target_bp.ruleset_version or settings.ruleset_version)
    else:
        if not req.target_replay_id:
            raise HTTPException(status_code=400, detail="target_replay_id required")
        target_replay = db.get(Replay, req.target_replay_id)
        if not target_replay:
            raise HTTPException(status_code=404, detail="Replay not found")
        target_match = db.get(Match, target_replay.match_id)
        mode = str(getattr(target_match, "mode", "") or "1v1")
        ruleset = str(
            getattr(target_match, "ruleset_version", "") or settings.ruleset_version
        )
        if target_match and target_match.blueprint_a_id:
            target_bp = db.get(Blueprint, target_match.blueprint_a_id)

    if ruleset != settings.ruleset_version:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ruleset_mismatch",
                "expected": settings.ruleset_version,
                "got": ruleset,
            },
        )

    s, e = _clamp_seconds(start=req.start, end=req.end)

    challenge_id = f"ch_{uuid4().hex}"
    mods: dict[str, Any] | None = None
    if target_match and getattr(target_match, "portal_id", None):
        try:
            aug_a = orjson.loads(getattr(target_match, "augments_a_json", "[]") or "[]")
            aug_b = orjson.loads(getattr(target_match, "augments_b_json", "[]") or "[]")
            if isinstance(aug_a, list) and isinstance(aug_b, list):
                mods = {
                    "portal_id": str(target_match.portal_id),
                    "augments_a": aug_a,
                    "augments_b": aug_b,
                }
        except Exception:  # noqa: BLE001
            mods = None
    if mods is None:
        mods = select_match_modifiers(challenge_id)

    ch = Challenge(
        id=challenge_id,
        kind=req.kind,
        target_blueprint_id=target_bp.id if target_bp else None,
        target_replay_id=target_replay.id if target_replay else None,
        start_sec=s,
        end_sec=e,
        mode=mode,
        ruleset_version=ruleset,
        week_id=None,
        portal_id=str(mods.get("portal_id") or "") if mods else None,
        augments_a_json=orjson.dumps(mods.get("augments_a") or []).decode("utf-8")
        if mods
        else "[]",
        augments_b_json=orjson.dumps(mods.get("augments_b") or []).decode("utf-8")
        if mods
        else "[]",
        creator_user_id=user_id,
        status="active",
        created_at=now,
    )
    db.add(ch)
    db.commit()

    return ChallengeCreateResponse(
        challenge_id=challenge_id, share_url=f"/s/challenge/{challenge_id}"
    )


class ChallengeAuthorOut(BaseModel):
    user_id: str | None = None
    display_name: str | None = None


class ChallengeOut(BaseModel):
    id: str
    kind: str
    mode: Literal["1v1", "team"]
    ruleset_version: str
    target_blueprint_id: str | None = None
    target_replay_id: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    portal_id: str | None = None
    augments_a: list[dict[str, Any]] = Field(default_factory=list)
    augments_b: list[dict[str, Any]] = Field(default_factory=list)
    creator: ChallengeAuthorOut
    created_at: datetime
    status: str
    attempts_total: int
    wins_total: int


@router.get("/{challenge_id}", response_model=ChallengeOut)
def get_challenge(
    challenge_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ChallengeOut:
    ch = db.get(Challenge, challenge_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")

    creator = db.get(User, ch.creator_user_id) if ch.creator_user_id else None

    attempts_total = int(
        db.scalar(
            select(func.count(ChallengeAttempt.id)).where(
                ChallengeAttempt.challenge_id == ch.id
            )
        )
        or 0
    )
    wins_total = int(
        db.scalar(
            select(func.count(ChallengeAttempt.id))
            .join(Match, Match.id == ChallengeAttempt.match_id)
            .where(ChallengeAttempt.challenge_id == ch.id)
            .where(Match.status == "done")
            .where(Match.result == "A")
        )
        or 0
    )

    aug_a: list[dict[str, Any]] = []
    aug_b: list[dict[str, Any]] = []
    try:
        aug_a = orjson.loads(ch.augments_a_json or "[]") if ch.augments_a_json else []
    except Exception:  # noqa: BLE001
        aug_a = []
    try:
        aug_b = orjson.loads(ch.augments_b_json or "[]") if ch.augments_b_json else []
    except Exception:  # noqa: BLE001
        aug_b = []

    return ChallengeOut(
        id=ch.id,
        kind=ch.kind,
        mode=ch.mode,  # type: ignore[arg-type]
        ruleset_version=ch.ruleset_version,
        target_blueprint_id=ch.target_blueprint_id,
        target_replay_id=ch.target_replay_id,
        start_sec=ch.start_sec,
        end_sec=ch.end_sec,
        portal_id=ch.portal_id,
        augments_a=aug_a if isinstance(aug_a, list) else [],
        augments_b=aug_b if isinstance(aug_b, list) else [],
        creator=ChallengeAuthorOut(
            user_id=ch.creator_user_id,
            display_name=creator.display_name if creator else None,
        ),
        created_at=ch.created_at,
        status=ch.status,
        attempts_total=attempts_total,
        wins_total=wins_total,
    )


class ChallengeAcceptRequest(BaseModel):
    blueprint_id: str | None = None
    seed_set_count: int = Field(default=1, ge=1, le=9)


class ChallengeAcceptResponse(BaseModel):
    attempt_id: str
    match_id: str
    status: Literal["queued", "running"]


@router.post("/{challenge_id}/accept", response_model=ChallengeAcceptResponse)
def accept_challenge(
    request: Request,
    challenge_id: str,
    req: ChallengeAcceptRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ChallengeAcceptResponse:
    ch = db.get(Challenge, challenge_id)
    if not ch or ch.status != "active":
        raise HTTPException(status_code=404, detail="Challenge not found")

    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="challenge_accept",
        per_minute_user=int(settings.rate_limit_challenge_accept_per_minute),
        per_hour_user=int(settings.rate_limit_challenge_accept_per_hour),
        per_minute_ip=int(settings.rate_limit_challenge_accept_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_challenge_accept_per_hour_ip),
        extra_detail={"challenge_id": challenge_id},
    )

    now = datetime.now(UTC)
    daily_limit = 10
    since = now - timedelta(days=1)
    recent_count = int(
        db.scalar(
            select(func.count(ChallengeAttempt.id))
            .where(ChallengeAttempt.challenge_id == ch.id)
            .where(ChallengeAttempt.challenger_user_id == user_id)
            .where(ChallengeAttempt.created_at >= since)
        )
        or 0
    )
    if recent_count >= daily_limit:
        retry_after = 3600
        raise HTTPException(
            status_code=429,
            detail={
                "error": "challenge_rate_limited",
                "retry_after_sec": retry_after,
                "daily_limit": daily_limit,
            },
            headers={"Retry-After": str(int(retry_after))},
        )

    attempt_index = (
        int(
            db.scalar(
                select(func.count(ChallengeAttempt.id))
                .where(ChallengeAttempt.challenge_id == ch.id)
                .where(ChallengeAttempt.challenger_user_id == user_id)
            )
            or 0
        )
        + 1
    )

    match_id = derive_challenge_match_id(
        challenge_id=ch.id,
        challenger_id=user_id,
        attempt_index=attempt_index,
    )

    # Challenger spec.
    bp_a: Blueprint | None = None
    if req.blueprint_id:
        cand = db.get(Blueprint, req.blueprint_id)
        if cand and cand.user_id == user_id and cand.status == "submitted":
            bp_a = cand
    if bp_a is None:
        bp_a = db.scalar(
            select(Blueprint)
            .where(Blueprint.user_id == user_id)
            .where(Blueprint.status == "submitted")
            .where(Blueprint.mode == ch.mode)
            .where(Blueprint.ruleset_version == ch.ruleset_version)
            .order_by(desc(Blueprint.submitted_at), desc(Blueprint.updated_at))
            .limit(1)
        )

    if bp_a:
        spec_a_dict = orjson.loads(bp_a.spec_json)
        blueprint_a_id = bp_a.id
    else:
        spec_a_dict = _default_spec(ch.mode, ch.ruleset_version)  # type: ignore[arg-type]
        blueprint_a_id = None
    BlueprintSpec.model_validate(spec_a_dict)

    # Opponent spec (target build).
    bp_b: Blueprint | None = (
        db.get(Blueprint, ch.target_blueprint_id) if ch.target_blueprint_id else None
    )
    if bp_b is None and ch.target_replay_id:
        replay = db.get(Replay, ch.target_replay_id)
        match = db.get(Match, replay.match_id) if replay else None
        if match and match.blueprint_a_id:
            bp_b = db.get(Blueprint, match.blueprint_a_id)
        elif match and match.blueprint_b_id:
            bp_b = db.get(Blueprint, match.blueprint_b_id)
    if bp_b is None:
        bp_b = _pick_bot_blueprint(db, mode=str(ch.mode), seed=match_id)
    if bp_b.status != "submitted":
        raise HTTPException(status_code=404, detail="Opponent build not available")
    spec_b_dict = orjson.loads(bp_b.spec_json)
    BlueprintSpec.model_validate(spec_b_dict)

    if ch.mode != bp_b.mode:
        raise HTTPException(status_code=400, detail="Challenge mode mismatch")

    settings = Settings()
    if db.get(Match, match_id) is None:
        match = Match(
            id=match_id,
            queue_type="challenge",
            week_id=ch.week_id,
            mode=ch.mode,
            ruleset_version=ch.ruleset_version,
            portal_id=ch.portal_id,
            augments_a_json=ch.augments_a_json or "[]",
            augments_b_json=ch.augments_b_json or "[]",
            seed_set_count=int(req.seed_set_count),
            user_a_id=user_id,
            user_b_id=bp_b.user_id,
            blueprint_a_id=blueprint_a_id,
            blueprint_b_id=bp_b.id,
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

    attempt = ChallengeAttempt(
        id=f"ca_{uuid4().hex}",
        challenge_id=ch.id,
        challenger_user_id=user_id,
        attempt_index=int(attempt_index),
        match_id=match_id,
        result="pending",
        created_at=now,
    )
    db.add(attempt)
    try:
        ev = log_event(
            db,
            type="challenge_accept",
            user_id=user_id,
            request=request,
            payload={
                "challenge_id": str(ch.id),
                "attempt_id": str(attempt.id),
                "match_id": str(match_id),
                "mode": str(ch.mode or ""),
                "ruleset_version": str(ch.ruleset_version or ""),
                "seed_set_count": int(req.seed_set_count or 1),
            },
            now=now,
        )
        try:
            from neuroleague_api.quests_engine import apply_event_to_quests

            apply_event_to_quests(db, event=ev)
        except Exception:  # noqa: BLE001
            pass

        try:
            ev2 = log_event(
                db,
                type="quest_remix_or_beat",
                user_id=user_id,
                request=request,
                payload={
                    "source": "challenge_accept",
                    "challenge_id": str(ch.id),
                    "attempt_id": str(attempt.id),
                },
                now=now,
            )
            try:
                from neuroleague_api.quests_engine import apply_event_to_quests

                apply_event_to_quests(db, event=ev2)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    db.commit()

    if os.environ.get("NEUROLEAGUE_E2E_FAST") == "1":
        match = db.get(Match, match_id)
        if match:
            try:
                run_match_sync(
                    db=db,
                    match=match,
                    blueprint_a=spec_a_dict,
                    blueprint_b=spec_b_dict,
                    user_a_id=str(user_id),
                    user_b_id=str(bp_b.user_id),
                    mode=str(ch.mode),
                    ruleset_version=str(ch.ruleset_version),
                    seed_set_count=int(req.seed_set_count),
                    queue_type="challenge",
                    update_ratings=False,
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
            seed_set_count=int(req.seed_set_count),
            blueprint_a=spec_a_dict,
            blueprint_b=spec_b_dict,
            user_a_id=user_id,
            user_b_id=bp_b.user_id,
            mode=str(ch.mode),
            ruleset_version=str(ch.ruleset_version),
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
            queue_type="challenge",
            update_ratings=False,
        )
        match = db.get(Match, match_id)
        if match:
            match.ray_job_id = obj_ref.hex()
            db.add(match)
            db.commit()

    return ChallengeAcceptResponse(
        attempt_id=attempt.id, match_id=match_id, status="queued"
    )


class ChallengeLeaderboardRow(BaseModel):
    rank: int
    user_id: str
    display_name: str
    wins: int
    attempts: int


@router.get("/{challenge_id}/leaderboard", response_model=list[ChallengeLeaderboardRow])
def leaderboard(
    challenge_id: str,
    limit: int = 50,
    db: Session = DBSession,
) -> list[ChallengeLeaderboardRow]:
    ch = db.get(Challenge, challenge_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")

    wins_expr = func.sum(case((Match.result == "A", 1), else_=0))
    cnt_expr = func.count(ChallengeAttempt.id)
    rows = db.execute(
        select(
            ChallengeAttempt.challenger_user_id,
            cnt_expr,
            wins_expr,
        )
        .join(Match, Match.id == ChallengeAttempt.match_id)
        .where(ChallengeAttempt.challenge_id == ch.id)
        .where(Match.status == "done")
        .group_by(ChallengeAttempt.challenger_user_id)
        .order_by(desc(wins_expr), cnt_expr, ChallengeAttempt.challenger_user_id.asc())
        .limit(int(limit))
    ).all()

    user_ids = sorted({str(uid) for uid, _cnt, _wins in rows if uid})
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    user_by_id = {u.id: u for u in users}

    out: list[ChallengeLeaderboardRow] = []
    for idx, (uid, cnt, wins) in enumerate(rows, start=1):
        u = user_by_id.get(str(uid))
        out.append(
            ChallengeLeaderboardRow(
                rank=idx,
                user_id=str(uid),
                display_name=u.display_name if u else "Lab_Unknown",
                wins=int(wins or 0),
                attempts=int(cnt or 0),
            )
        )
    return out
