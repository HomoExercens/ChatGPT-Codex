from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.core.config import Settings
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import (
    Blueprint,
    Cosmetic,
    Follow,
    Match,
    Quest,
    QuestAssignment,
    Rating,
    Referral,
    Replay,
    User,
    UserCosmetic,
)
from neuroleague_api.rate_limit import check_rate_limit_dual

router = APIRouter(prefix="/api/users", tags=["users"])


class UserSummaryOut(BaseModel):
    id: str
    display_name: str
    is_guest: bool
    avatar_url: str | None = None


class RatingOut(BaseModel):
    mode: Literal["1v1", "team"]
    elo: int
    games_played: int


class BlueprintSummaryOut(BaseModel):
    id: str
    name: str
    mode: Literal["1v1", "team"]
    ruleset_version: str
    submitted_at: datetime | None = None


class ProfileMatchOut(BaseModel):
    id: str
    created_at: datetime
    status: str
    result: Literal["win", "loss", "draw"] | None = None
    opponent_display_name: str
    opponent_user_id: str | None = None
    opponent_type: Literal["human", "bot"]
    replay_id: str | None = None


class BadgeOut(BaseModel):
    id: str
    name: str
    earned_at: datetime
    source: str


class ReferralOut(BaseModel):
    id: str
    new_user_id: str
    new_user_display_name: str | None = None
    status: str
    created_at: datetime
    credited_at: datetime | None = None


class QuestHistoryOut(BaseModel):
    period_key: str
    cadence: str
    key: str
    title: str
    progress_count: int
    goal_count: int
    claimed_at: str | None = None


class UserProfileOut(BaseModel):
    user: UserSummaryOut
    rating: RatingOut
    latest_submitted_blueprint: BlueprintSummaryOut | None = None
    recent_matches: list[ProfileMatchOut]
    follower_count: int = 0
    following_count: int = 0
    is_following: bool = False
    badges: list[BadgeOut] = []
    referrals: list[ReferralOut] = []
    quest_history: list[QuestHistoryOut] = []


@router.get("/{user_id}/profile", response_model=UserProfileOut)
def profile(
    user_id: str,
    mode: Literal["1v1", "team"] = "1v1",
    _viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> UserProfileOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    follower_count = int(
        db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.followee_user_id == user_id)
        )
        or 0
    )
    following_count = int(
        db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.follower_user_id == user_id)
        )
        or 0
    )
    is_following = (
        db.get(
            Follow, {"follower_user_id": _viewer_user_id, "followee_user_id": user_id}
        )
        is not None
        if _viewer_user_id != user_id
        else False
    )

    rating = db.get(Rating, {"user_id": user_id, "mode": mode})
    rating_out = RatingOut(
        mode=mode,
        elo=int(rating.elo) if rating else 1000,
        games_played=int(rating.games_played) if rating else 0,
    )

    bp = db.scalar(
        select(Blueprint)
        .where(Blueprint.user_id == user_id)
        .where(Blueprint.mode == mode)
        .where(Blueprint.status == "submitted")
        .order_by(desc(Blueprint.submitted_at), desc(Blueprint.updated_at))
        .limit(1)
    )
    bp_out: BlueprintSummaryOut | None = None
    if bp:
        bp_out = BlueprintSummaryOut(
            id=bp.id,
            name=bp.name,
            mode=bp.mode,  # type: ignore[arg-type]
            ruleset_version=bp.ruleset_version,
            submitted_at=bp.submitted_at,
        )

    matches = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.mode == mode)
        .where(Match.queue_type == "ranked")
        .order_by(desc(Match.created_at))
        .limit(10)
    ).all()

    match_ids = [m.id for m in matches]
    replays = (
        db.scalars(select(Replay).where(Replay.match_id.in_(match_ids))).all()
        if match_ids
        else []
    )
    replay_by_match: dict[str, str] = {r.match_id: r.id for r in replays}

    opp_ids = sorted({m.user_b_id for m in matches if m.user_b_id})
    opp_users = (
        db.scalars(select(User).where(User.id.in_(opp_ids))).all() if opp_ids else []
    )
    opp_by_id: dict[str, User] = {u.id: u for u in opp_users}

    out_matches: list[ProfileMatchOut] = []
    for m in matches:
        opp_id = m.user_b_id
        opp_user = opp_by_id.get(opp_id) if opp_id else None
        opp_name = opp_user.display_name if opp_user else "Lab_Unknown"
        opp_type: Literal["human", "bot"] = (
            "bot" if (opp_id or "").startswith("bot_") else "human"
        )
        result: Literal["win", "loss", "draw"] | None = None
        if m.status == "done":
            result = "win" if m.result == "A" else "loss" if m.result == "B" else "draw"
        out_matches.append(
            ProfileMatchOut(
                id=m.id,
                created_at=m.created_at,
                status=m.status,
                result=result,
                opponent_display_name=opp_name,
                opponent_user_id=opp_id,
                opponent_type=opp_type,
                replay_id=replay_by_match.get(m.id),
            )
        )

    badges_rows = db.execute(
        select(UserCosmetic, Cosmetic)
        .join(Cosmetic, Cosmetic.id == UserCosmetic.cosmetic_id)
        .where(UserCosmetic.user_id == user_id)
        .where(Cosmetic.kind == "badge")
        .order_by(desc(UserCosmetic.earned_at), Cosmetic.id.asc())
    ).all()

    badges_out = [
        BadgeOut(id=c.id, name=c.name, earned_at=uc.earned_at, source=uc.source)
        for (uc, c) in badges_rows
    ]

    referrals_out: list[ReferralOut] = []
    if _viewer_user_id == user_id:
        referrals = db.scalars(
            select(Referral)
            .where(Referral.creator_user_id == user_id)
            .order_by(desc(Referral.created_at))
            .limit(5)
        ).all()
        new_ids = sorted({r.new_user_id for r in referrals if r.new_user_id})
        new_users = (
            db.scalars(select(User).where(User.id.in_(new_ids))).all()
            if new_ids
            else []
        )
        new_by_id: dict[str, User] = {u.id: u for u in new_users}
        referrals_out = [
            ReferralOut(
                id=r.id,
                new_user_id=r.new_user_id,
                new_user_display_name=new_by_id.get(r.new_user_id).display_name
                if new_by_id.get(r.new_user_id)
                else None,
                status=r.status,
                created_at=r.created_at,
                credited_at=r.credited_at,
            )
            for r in referrals
        ]

    quest_history: list[QuestHistoryOut] = []
    if _viewer_user_id == user_id:
        try:
            from zoneinfo import ZoneInfo

            kst_today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Seoul")).date()
            keys = [
                (kst_today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)
            ]
        except Exception:  # noqa: BLE001
            keys = []

        if keys:
            rows = db.execute(
                select(QuestAssignment, Quest)
                .join(Quest, Quest.id == QuestAssignment.quest_id)
                .where(QuestAssignment.user_id == user_id)
                .where(Quest.cadence == "daily")
                .where(QuestAssignment.period_key.in_(keys))
                .order_by(desc(QuestAssignment.period_key), Quest.key.asc())
                .limit(50)
            ).all()
            quest_history = [
                QuestHistoryOut(
                    period_key=str(a.period_key),
                    cadence=str(q.cadence),
                    key=str(q.key),
                    title=str(q.title),
                    progress_count=int(a.progress_count or 0),
                    goal_count=int(q.goal_count or 1),
                    claimed_at=a.claimed_at.isoformat() if a.claimed_at else None,
                )
                for (a, q) in rows
            ]

    return UserProfileOut(
        user=UserSummaryOut(
            id=user.id,
            display_name=user.display_name,
            is_guest=bool(user.is_guest),
            avatar_url=user.avatar_url,
        ),
        rating=rating_out,
        latest_submitted_blueprint=bp_out,
        recent_matches=out_matches,
        follower_count=follower_count,
        following_count=following_count,
        is_following=is_following,
        badges=badges_out,
        referrals=referrals_out,
        quest_history=quest_history,
    )


class FollowToggleOut(BaseModel):
    ok: bool = True
    following: bool
    follower_count: int
    following_count: int


@router.post("/{user_id}/follow", response_model=FollowToggleOut)
def toggle_follow(
    request: Request,
    user_id: str,
    viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> FollowToggleOut:
    if viewer_user_id == user_id:
        raise HTTPException(status_code=400, detail="cannot_follow_self")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user_not_found")

    settings = Settings()
    check_rate_limit_dual(
        user_id=viewer_user_id,
        request=request,
        action="follow",
        per_minute_user=int(settings.rate_limit_follow_per_minute),
        per_hour_user=int(settings.rate_limit_follow_per_hour),
        per_minute_ip=int(settings.rate_limit_follow_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_follow_per_hour_ip),
        extra_detail={"target_user_id": user_id},
    )

    existing = db.get(
        Follow, {"follower_user_id": viewer_user_id, "followee_user_id": user_id}
    )
    following = False
    if existing:
        db.delete(existing)
        following = False
    else:
        db.add(
            Follow(
                follower_user_id=viewer_user_id,
                followee_user_id=user_id,
                created_at=datetime.now(UTC),
            )
        )
        following = True
    db.commit()

    follower_count = int(
        db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.followee_user_id == user_id)
        )
        or 0
    )
    following_count = int(
        db.scalar(
            select(func.count())
            .select_from(Follow)
            .where(Follow.follower_user_id == viewer_user_id)
        )
        or 0
    )

    try:
        log_event(
            db,
            type="follow" if following else "unfollow",
            user_id=viewer_user_id,
            request=request,
            payload={"target_user_id": user_id},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    return FollowToggleOut(
        following=following,
        follower_count=follower_count,
        following_count=following_count,
    )
