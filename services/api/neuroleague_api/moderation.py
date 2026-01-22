from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from neuroleague_api.models import UserSoftBan


def ensure_not_soft_banned(
    db: Session, *, user_id: str, now: datetime | None = None
) -> None:
    now_dt = now or datetime.now(UTC)
    ban = db.get(UserSoftBan, str(user_id))
    if not ban:
        return
    banned_until = getattr(ban, "banned_until", None)
    if banned_until is None:
        return
    if getattr(banned_until, "tzinfo", None) is None:
        banned_until = banned_until.replace(tzinfo=UTC)
    if getattr(now_dt, "tzinfo", None) is None:
        now_dt = now_dt.replace(tzinfo=UTC)
    if banned_until <= now_dt:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "soft_banned",
            "banned_until": banned_until.isoformat(),
            "reason": (ban.reason or "").strip() or None,
        },
    )
