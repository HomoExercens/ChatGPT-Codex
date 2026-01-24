from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from neuroleague_api.models import Cosmetic, UserCosmetic, UserProgress
from neuroleague_api.storage import load_replay_json


BadgeKind = Literal["PERFECT", "ONE-SHOT", "CLUTCH"]


def _kst_today_date(*, now_utc: datetime) -> date:
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("Asia/Seoul")).date()
    except Exception:  # noqa: BLE001
        return now_utc.date()


def level_for_xp(xp: int) -> int:
    return max(1, int(xp) // 100 + 1)


def _ensure_progress(session: Session, *, user_id: str, now: datetime) -> UserProgress:
    row = session.get(UserProgress, str(user_id))
    if row is not None:
        return row
    row = UserProgress(
        user_id=str(user_id),
        xp=0,
        level=1,
        streak_days=0,
        last_active_day=None,
        quests_claimed_total=0,
        perfect_wins=0,
        one_shot_wins=0,
        clutch_wins=0,
        updated_at=now,
    )
    session.add(row)
    return row


@dataclass(frozen=True)
class QuestRewardResult:
    xp_awarded: int
    xp_total: int
    level: int
    level_up: bool
    streak_days: int
    streak_extended: bool
    badges_unlocked: list[str]


def _ensure_badge_cosmetic(session: Session, *, cosmetic_id: str, name: str, now: datetime) -> None:
    if session.get(Cosmetic, cosmetic_id) is not None:
        return
    session.add(
        Cosmetic(
            id=str(cosmetic_id),
            kind="badge",
            name=str(name)[:120],
            asset_path=None,
            created_at=now,
        )
    )


def _grant_badge(
    session: Session,
    *,
    user_id: str,
    cosmetic_id: str,
    name: str,
    now: datetime,
    source: str,
) -> bool:
    _ensure_badge_cosmetic(session, cosmetic_id=cosmetic_id, name=name, now=now)
    existing = session.get(UserCosmetic, {"user_id": str(user_id), "cosmetic_id": str(cosmetic_id)})
    if existing is not None:
        return False
    session.add(
        UserCosmetic(
            user_id=str(user_id),
            cosmetic_id=str(cosmetic_id),
            earned_at=now,
            source=str(source)[:120],
        )
    )
    return True


def _badge_unlocks_for_progress(row: UserProgress) -> list[tuple[str, str, str]]:
    """
    Returns (cosmetic_id, name, source) unlocks that *should* be granted based on counters.
    """
    unlocks: list[tuple[str, str, str]] = []
    if int(row.quests_claimed_total or 0) >= 3:
        unlocks.append(("badge_quest_claim_3", "Quest Claimer I", "quest_claim_total_3"))
    if int(row.streak_days or 0) >= 3:
        unlocks.append(("badge_streak_3", "Streak 3", "streak_3"))
    if int(row.level or 1) >= 5:
        unlocks.append(("badge_level_5", "Level 5", "level_5"))
    if int(row.perfect_wins or 0) >= 1:
        unlocks.append(("badge_perfect", "PERFECT", "perfect_win_1"))
    if int(row.one_shot_wins or 0) >= 1:
        unlocks.append(("badge_one_shot", "ONE-SHOT", "one_shot_win_1"))
    if int(row.clutch_wins or 0) >= 1:
        unlocks.append(("badge_clutch", "CLUTCH", "clutch_win_1"))
    return unlocks


def apply_badge_unlocks(
    session: Session,
    *,
    user_id: str,
    now: datetime,
) -> list[str]:
    row = session.get(UserProgress, str(user_id))
    if row is None:
        return []
    unlocked: list[str] = []
    for cosmetic_id, name, source in _badge_unlocks_for_progress(row):
        if _grant_badge(
            session,
            user_id=user_id,
            cosmetic_id=cosmetic_id,
            name=name,
            now=now,
            source=source,
        ):
            unlocked.append(str(cosmetic_id))
    return unlocked


def apply_quest_claim_rewards(
    session: Session,
    *,
    user_id: str,
    cadence: str,
    quest_key: str,
    now: datetime,
) -> QuestRewardResult:
    row = _ensure_progress(session, user_id=user_id, now=now)
    before_level = int(row.level or 1)

    xp_awarded = 25 if str(cadence) == "daily" else 100
    row.xp = int(row.xp or 0) + int(xp_awarded)
    row.level = level_for_xp(int(row.xp or 0))
    row.quests_claimed_total = int(row.quests_claimed_total or 0) + 1

    today = _kst_today_date(now_utc=now)
    streak_extended = False
    if row.last_active_day != today:
        streak_extended = True
        if row.last_active_day is not None and row.last_active_day == today - timedelta(days=1):
            row.streak_days = int(row.streak_days or 0) + 1
        else:
            row.streak_days = 1
        row.last_active_day = today

    row.updated_at = now
    session.add(row)

    badges_unlocked = apply_badge_unlocks(session, user_id=user_id, now=now)

    return QuestRewardResult(
        xp_awarded=int(xp_awarded),
        xp_total=int(row.xp or 0),
        level=int(row.level or 1),
        level_up=int(row.level or 1) > before_level,
        streak_days=int(row.streak_days or 0),
        streak_extended=bool(streak_extended),
        badges_unlocked=badges_unlocked,
    )


def _challenge_badge_from_replay(payload: dict[str, Any]) -> BadgeKind | None:
    end = payload.get("end_summary") if isinstance(payload.get("end_summary"), dict) else {}
    winner = str(end.get("winner") or "")
    if winner != "A":
        return None
    duration_ticks = int(end.get("duration_ticks") or 0)
    hp_a = int(end.get("hp_a") or 0)

    max_a = 0
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    units = header.get("units") if isinstance(header.get("units"), list) else []
    for u in units:
        if isinstance(u, dict) and str(u.get("team") or "") == "A":
            max_a += int(u.get("max_hp") or 0)

    if max_a > 0 and hp_a == max_a:
        return "PERFECT"
    if duration_ticks > 0 and duration_ticks <= 90:
        return "ONE-SHOT"
    return "CLUTCH"


def apply_challenge_win_badge(
    session: Session,
    *,
    user_id: str,
    replay_artifact_path: str,
    now: datetime,
) -> tuple[BadgeKind | None, list[str]]:
    payload = load_replay_json(artifact_path=replay_artifact_path)
    if not isinstance(payload, dict):
        return None, []
    badge = _challenge_badge_from_replay(payload)
    if badge is None:
        return None, []

    row = _ensure_progress(session, user_id=user_id, now=now)
    if badge == "PERFECT":
        row.perfect_wins = int(row.perfect_wins or 0) + 1
    elif badge == "ONE-SHOT":
        row.one_shot_wins = int(row.one_shot_wins or 0) + 1
    else:
        row.clutch_wins = int(row.clutch_wins or 0) + 1
    row.updated_at = now
    session.add(row)
    unlocked = apply_badge_unlocks(session, user_id=user_id, now=now)
    return badge, unlocked
