from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import (
    Cosmetic,
    Quest,
    QuestAssignment,
    UserCosmetic,
    Wallet,
)
from neuroleague_api.quests_engine import (
    QUESTS_OVERRIDE_KEY,
    ensure_assignments,
    kst_today_key,
    kst_week_key,
    load_quest_overrides,
    select_quests_for_period,
    write_quest_overrides,
)


Cadence = Literal["daily", "weekly"]


def _require_admin(x_admin_token: str | None) -> None:
    settings = Settings()
    expected = str(settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=401, detail="admin_disabled")
    if str(x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class QuestDefOut(BaseModel):
    id: str
    cadence: Cadence
    key: str
    title: str
    description: str
    goal_count: int
    event_type: str
    filters: dict[str, Any] = Field(default_factory=dict)
    reward_cosmetic_id: str
    reward_amount: int = 1
    active_from: datetime | None = None
    active_to: datetime | None = None


class QuestAssignmentOut(BaseModel):
    assignment_id: str
    period_key: str
    progress_count: int
    claimed_at: datetime | None = None
    claimable: bool
    quest: QuestDefOut


class QuestsTodayOut(BaseModel):
    server_time_kst: str
    ruleset_version: str
    daily_period_key: str
    weekly_period_key: str
    daily: list[QuestAssignmentOut]
    weekly: list[QuestAssignmentOut]


class ClaimQuestIn(BaseModel):
    assignment_id: str = Field(min_length=1, max_length=80)


class ClaimQuestOut(BaseModel):
    ok: bool = True
    assignment_id: str
    claimed_at: datetime
    reward_cosmetic_id: str
    reward_granted: bool
    cosmetic_points_awarded: int = 0
    cosmetic_points_balance: int | None = None
    xp_awarded: int = 0
    xp_total: int = 0
    level: int = 1
    level_up: bool = False
    streak_days: int = 0
    streak_extended: bool = False
    badges_unlocked: list[str] = Field(default_factory=list)


class OpsQuestUpsertIn(BaseModel):
    id: str | None = None
    cadence: Cadence
    key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=400)
    goal_count: int = Field(default=1, ge=1, le=1000)
    event_type: str = Field(min_length=1, max_length=80)
    filters: dict[str, Any] = Field(default_factory=dict)
    reward_cosmetic_id: str = Field(min_length=1, max_length=120)
    reward_amount: int = Field(default=1, ge=1, le=100)
    active_from: datetime | None = None
    active_to: datetime | None = None


class OpsOverrideIn(BaseModel):
    cadence: Cadence
    quest_keys: list[str] = Field(default_factory=list)
    period_key: str | None = None
    clear: bool = False


class OpsQuestsOut(BaseModel):
    server_time_kst: str
    ruleset_version: str
    daily_period_key: str
    weekly_period_key: str
    daily_selected: list[QuestDefOut]
    weekly_selected: list[QuestDefOut]
    overrides: dict[str, Any] = Field(default_factory=dict)
    all_quests: list[QuestDefOut]
    storage_key: str = QUESTS_OVERRIDE_KEY


router = APIRouter(prefix="/api/quests", tags=["quests"])
ops_router = APIRouter(prefix="/api/ops/quests", tags=["ops"])


def _quest_to_out(q: Quest) -> QuestDefOut:
    try:
        filt = orjson.loads((q.filters_json or "{}").encode("utf-8"))
    except Exception:  # noqa: BLE001
        filt = {}
    if not isinstance(filt, dict):
        filt = {}
    return QuestDefOut(
        id=str(q.id),
        cadence=str(q.cadence),  # type: ignore[arg-type]
        key=str(q.key),
        title=str(q.title),
        description=str(q.description or ""),
        goal_count=int(q.goal_count or 1),
        event_type=str(q.event_type),
        filters=filt,
        reward_cosmetic_id=str(q.reward_cosmetic_id),
        reward_amount=int(q.reward_amount or 1),
        active_from=q.active_from,
        active_to=q.active_to,
    )


def _assignment_out(*, a: QuestAssignment, q: Quest) -> QuestAssignmentOut:
    goal = int(q.goal_count or 1)
    progress = int(a.progress_count or 0)
    return QuestAssignmentOut(
        assignment_id=str(a.id),
        period_key=str(a.period_key),
        progress_count=progress,
        claimed_at=a.claimed_at,
        claimable=(a.claimed_at is None and progress >= goal),
        quest=_quest_to_out(q),
    )


@router.get("/today", response_model=QuestsTodayOut)
def today(
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> QuestsTodayOut:
    now = datetime.now(UTC)
    settings = Settings()
    overrides = load_quest_overrides()
    daily_key = kst_today_key(now_utc=now)
    weekly_key = kst_week_key(now_utc=now)

    daily = select_quests_for_period(
        db,
        cadence="daily",
        period_key=daily_key,
        limit=3,
        now=now,
        overrides=overrides,
    )
    weekly = select_quests_for_period(
        db,
        cadence="weekly",
        period_key=weekly_key,
        limit=3,
        now=now,
        overrides=overrides,
    )

    daily_assignments = []
    weekly_assignments = []
    if daily:
        daily_assignments = ensure_assignments(
            db, user_id=user_id, period_key=daily_key, quests=daily, now=now
        )
    if weekly:
        weekly_assignments = ensure_assignments(
            db, user_id=user_id, period_key=weekly_key, quests=weekly, now=now
        )
    if daily_assignments or weekly_assignments:
        db.commit()

    daily_by_id = {str(q.id): q for q in daily}
    weekly_by_id = {str(q.id): q for q in weekly}
    daily_out = [
        _assignment_out(a=a, q=daily_by_id.get(str(a.quest_id)))
        for a in daily_assignments
        if daily_by_id.get(str(a.quest_id))
    ]
    weekly_out = [
        _assignment_out(a=a, q=weekly_by_id.get(str(a.quest_id)))
        for a in weekly_assignments
        if weekly_by_id.get(str(a.quest_id))
    ]

    try:
        from zoneinfo import ZoneInfo

        server_time_kst = now.astimezone(ZoneInfo("Asia/Seoul")).isoformat()
    except Exception:  # noqa: BLE001
        server_time_kst = now.isoformat()

    return QuestsTodayOut(
        server_time_kst=server_time_kst,
        ruleset_version=str(settings.ruleset_version),
        daily_period_key=daily_key,
        weekly_period_key=weekly_key,
        daily=daily_out,
        weekly=weekly_out,
    )


@router.post("/claim", response_model=ClaimQuestOut)
def claim(
    payload: ClaimQuestIn,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ClaimQuestOut:
    now = datetime.now(UTC)
    a = db.get(QuestAssignment, str(payload.assignment_id))
    if not a or str(a.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="assignment_not_found")
    q = db.get(Quest, str(a.quest_id))
    if not q:
        raise HTTPException(status_code=404, detail="quest_not_found")
    if a.claimed_at is not None:
        raise HTTPException(status_code=400, detail="already_claimed")

    goal = int(q.goal_count or 1)
    progress = int(a.progress_count or 0)
    if progress < goal:
        raise HTTPException(status_code=400, detail="not_complete")

    cosmetic_id = str(q.reward_cosmetic_id)
    if not cosmetic_id:
        raise HTTPException(status_code=500, detail="reward_missing")

    if db.get(Cosmetic, cosmetic_id) is None:
        db.add(
            Cosmetic(
                id=cosmetic_id,
                kind="badge",
                name=str(q.title),
                asset_path=None,
                created_at=now,
            )
        )

    existing = db.get(
        UserCosmetic, {"user_id": str(user_id), "cosmetic_id": cosmetic_id}
    )
    granted = False
    points_awarded = 0
    wallet = db.get(Wallet, str(user_id))
    if wallet is None:
        wallet = Wallet(user_id=str(user_id), tokens_balance=0, cosmetic_points=0)
        db.add(wallet)

    if existing is None:
        db.add(
            UserCosmetic(
                user_id=str(user_id),
                cosmetic_id=cosmetic_id,
                earned_at=now,
                source=f"quest_{q.cadence}_{q.key}_{a.period_key}",
            )
        )
        granted = True
    else:
        points_awarded = int(q.reward_amount or 1)
        wallet.cosmetic_points = int(wallet.cosmetic_points or 0) + points_awarded
        granted = False
        db.add(wallet)

    a.claimed_at = now
    db.add(a)

    reward = None
    try:
        from neuroleague_api.progression import apply_quest_claim_rewards

        reward = apply_quest_claim_rewards(
            db,
            user_id=str(user_id),
            cadence=str(q.cadence),
            quest_key=str(q.key),
            now=now,
        )
        if reward.streak_extended:
            log_event(
                db,
                type="streak_extended",
                user_id=str(user_id),
                request=None,
                payload={
                    "streak_days": int(reward.streak_days),
                    "cadence": str(q.cadence),
                    "key": str(q.key),
                    "assignment_id": str(a.id),
                    "period_key": str(a.period_key),
                },
                now=now,
            )
        if reward.level_up:
            log_event(
                db,
                type="level_up",
                user_id=str(user_id),
                request=None,
                payload={
                    "level": int(reward.level),
                    "xp_total": int(reward.xp_total),
                    "cadence": str(q.cadence),
                    "key": str(q.key),
                    "assignment_id": str(a.id),
                    "period_key": str(a.period_key),
                },
                now=now,
            )
        for bid in reward.badges_unlocked:
            log_event(
                db,
                type="badge_unlocked",
                user_id=str(user_id),
                request=None,
                payload={
                    "badge_id": str(bid),
                    "cadence": str(q.cadence),
                    "key": str(q.key),
                    "assignment_id": str(a.id),
                    "period_key": str(a.period_key),
                },
                now=now,
            )
    except Exception:  # noqa: BLE001
        reward = None

    try:
        log_event(
            db,
            type="quest_claim",
            user_id=str(user_id),
            request=None,
            payload={
                "assignment_id": str(a.id),
                "quest_id": str(q.id),
                "cadence": str(q.cadence),
                "key": str(q.key),
                "period_key": str(a.period_key),
                "reward_cosmetic_id": cosmetic_id,
                "reward_granted": granted,
                "cosmetic_points_awarded": points_awarded,
            },
            now=now,
        )
        log_event(
            db,
            type="quest_claimed",
            user_id=str(user_id),
            request=None,
            payload={
                "assignment_id": str(a.id),
                "quest_id": str(q.id),
                "cadence": str(q.cadence),
                "key": str(q.key),
                "period_key": str(a.period_key),
                "reward_cosmetic_id": cosmetic_id,
                "reward_granted": granted,
                "cosmetic_points_awarded": points_awarded,
            },
            now=now,
        )
    except Exception:  # noqa: BLE001
        pass

    db.commit()

    return ClaimQuestOut(
        ok=True,
        assignment_id=str(a.id),
        claimed_at=now,
        reward_cosmetic_id=cosmetic_id,
        reward_granted=granted,
        cosmetic_points_awarded=points_awarded,
        cosmetic_points_balance=int(wallet.cosmetic_points or 0),
        xp_awarded=int(getattr(reward, "xp_awarded", 0) or 0),
        xp_total=int(getattr(reward, "xp_total", 0) or 0),
        level=int(getattr(reward, "level", 1) or 1),
        level_up=bool(getattr(reward, "level_up", False) or False),
        streak_days=int(getattr(reward, "streak_days", 0) or 0),
        streak_extended=bool(getattr(reward, "streak_extended", False) or False),
        badges_unlocked=list(getattr(reward, "badges_unlocked", []) or []),
    )


@router.post("/claim/{quest_id}", response_model=ClaimQuestOut)
def claim_by_quest(
    quest_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ClaimQuestOut:
    now = datetime.now(UTC)
    overrides = load_quest_overrides()
    daily_key = kst_today_key(now_utc=now)
    weekly_key = kst_week_key(now_utc=now)

    daily = select_quests_for_period(
        db,
        cadence="daily",
        period_key=daily_key,
        limit=3,
        now=now,
        overrides=overrides,
    )
    weekly = select_quests_for_period(
        db,
        cadence="weekly",
        period_key=weekly_key,
        limit=3,
        now=now,
        overrides=overrides,
    )

    daily_assignments: list[QuestAssignment] = []
    weekly_assignments: list[QuestAssignment] = []
    if daily:
        daily_assignments = ensure_assignments(
            db, user_id=user_id, period_key=daily_key, quests=daily, now=now
        )
    if weekly:
        weekly_assignments = ensure_assignments(
            db, user_id=user_id, period_key=weekly_key, quests=weekly, now=now
        )
    if daily_assignments or weekly_assignments:
        db.commit()

    selected_ids = {str(q.id) for q in (daily + weekly)}
    q = db.get(Quest, str(quest_id))
    if q is None:
        q = db.scalar(select(Quest).where(Quest.key == str(quest_id)).limit(1))
    if q is None or str(q.id) not in selected_ids:
        raise HTTPException(status_code=404, detail="quest_not_selected")

    period_key = daily_key if str(q.cadence) == "daily" else weekly_key
    a = db.scalar(
        select(QuestAssignment)
        .where(QuestAssignment.user_id == str(user_id))
        .where(QuestAssignment.period_key == str(period_key))
        .where(QuestAssignment.quest_id == str(q.id))
        .limit(1)
    )
    if a is None:
        raise HTTPException(status_code=404, detail="assignment_not_found")

    return claim(payload=ClaimQuestIn(assignment_id=str(a.id)), user_id=user_id, db=db)


@ops_router.get("", response_model=OpsQuestsOut)
def ops_list(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsQuestsOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)
    settings = Settings()
    overrides = load_quest_overrides()
    daily_key = kst_today_key(now_utc=now)
    weekly_key = kst_week_key(now_utc=now)

    all_quests = db.scalars(select(Quest)).all()
    all_out = [_quest_to_out(q) for q in all_quests]
    daily_selected = select_quests_for_period(
        db,
        cadence="daily",
        period_key=daily_key,
        limit=3,
        now=now,
        overrides=overrides,
    )
    weekly_selected = select_quests_for_period(
        db,
        cadence="weekly",
        period_key=weekly_key,
        limit=3,
        now=now,
        overrides=overrides,
    )

    try:
        from zoneinfo import ZoneInfo

        server_time_kst = now.astimezone(ZoneInfo("Asia/Seoul")).isoformat()
    except Exception:  # noqa: BLE001
        server_time_kst = now.isoformat()

    return OpsQuestsOut(
        server_time_kst=server_time_kst,
        ruleset_version=str(settings.ruleset_version),
        daily_period_key=daily_key,
        weekly_period_key=weekly_key,
        daily_selected=[_quest_to_out(q) for q in daily_selected],
        weekly_selected=[_quest_to_out(q) for q in weekly_selected],
        overrides=overrides,
        all_quests=all_out,
    )


@ops_router.post("", response_model=QuestDefOut)
def ops_upsert(
    payload: OpsQuestUpsertIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> QuestDefOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)

    q: Quest | None = None
    if payload.id:
        q = db.get(Quest, str(payload.id))
    if q is None:
        q = db.scalar(
            select(Quest)
            .where(Quest.cadence == str(payload.cadence))
            .where(Quest.key == str(payload.key))
        )
    if q is None:
        q = Quest(
            id=f"q_{uuid4().hex}",
            cadence=str(payload.cadence),
            key=str(payload.key),
            title=str(payload.title),
            description=str(payload.description or ""),
            goal_count=int(payload.goal_count or 1),
            event_type=str(payload.event_type),
            filters_json=orjson.dumps(payload.filters or {}).decode("utf-8"),
            reward_cosmetic_id=str(payload.reward_cosmetic_id),
            reward_amount=int(payload.reward_amount or 1),
            active_from=payload.active_from,
            active_to=payload.active_to,
            created_at=now,
        )
        db.add(q)
        db.commit()
        return _quest_to_out(q)

    q.cadence = str(payload.cadence)
    q.key = str(payload.key)
    q.title = str(payload.title)
    q.description = str(payload.description or "")
    q.goal_count = int(payload.goal_count or 1)
    q.event_type = str(payload.event_type)
    q.filters_json = orjson.dumps(payload.filters or {}).decode("utf-8")
    q.reward_cosmetic_id = str(payload.reward_cosmetic_id)
    q.reward_amount = int(payload.reward_amount or 1)
    q.active_from = payload.active_from
    q.active_to = payload.active_to
    db.add(q)
    db.commit()
    return _quest_to_out(q)


@ops_router.post("/override", response_model=OpsQuestsOut)
def ops_override(
    payload: OpsOverrideIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsQuestsOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)

    overrides = load_quest_overrides()
    cadence = str(payload.cadence)
    if payload.clear:
        overrides.pop(cadence, None)
    else:
        period_key = payload.period_key
        if not period_key:
            period_key = (
                kst_today_key(now_utc=now)
                if cadence == "daily"
                else kst_week_key(now_utc=now)
            )
        overrides[cadence] = {
            "period_key": str(period_key),
            "quest_keys": [str(k) for k in payload.quest_keys if str(k).strip()][:10],
            "updated_at": now.isoformat(),
        }
    write_quest_overrides(overrides)
    return ops_list(x_admin_token=x_admin_token, db=db)
