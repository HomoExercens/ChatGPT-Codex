from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request

from neuroleague_api.core.config import Settings
from neuroleague_api.eventlog import ip_hash_from_request


@dataclass
class _Window:
    minute_start: int
    minute_count: int
    hour_start: int
    hour_count: int


_LOCK = Lock()
_STATE: dict[tuple[str, str], _Window] = {}


def _epoch_seconds(now: datetime) -> int:
    if getattr(now, "tzinfo", None) is None:
        now = now.replace(tzinfo=UTC)
    return int(now.timestamp())


def check_rate_limit(
    *,
    user_id: str,
    action: str,
    per_minute: int,
    per_hour: int,
    now: datetime | None = None,
    extra_detail: dict[str, Any] | None = None,
) -> None:
    settings = Settings()
    if not getattr(settings, "rate_limit_enabled", True):
        return

    if per_minute <= 0 and per_hour <= 0:
        return

    now_dt = now or datetime.now(UTC)
    now_s = _epoch_seconds(now_dt)
    minute_bucket = now_s // 60
    hour_bucket = now_s // 3600
    key = (str(user_id or "anon"), str(action))

    with _LOCK:
        w = _STATE.get(key)
        if w is None:
            w = _Window(
                minute_start=minute_bucket,
                minute_count=0,
                hour_start=hour_bucket,
                hour_count=0,
            )

        if w.minute_start != minute_bucket:
            w.minute_start = minute_bucket
            w.minute_count = 0
        if w.hour_start != hour_bucket:
            w.hour_start = hour_bucket
            w.hour_count = 0

        if per_minute > 0 and w.minute_count >= int(per_minute):
            retry_after = max(1, 60 - (now_s % 60))
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "action": action,
                    "retry_after_sec": retry_after,
                    **(extra_detail or {}),
                },
                headers={"Retry-After": str(int(retry_after))},
            )
        if per_hour > 0 and w.hour_count >= int(per_hour):
            retry_after = max(1, 3600 - (now_s % 3600))
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "action": action,
                    "retry_after_sec": retry_after,
                    **(extra_detail or {}),
                },
                headers={"Retry-After": str(int(retry_after))},
            )

        w.minute_count += 1
        w.hour_count += 1
        _STATE[key] = w


def check_rate_limit_dual(
    *,
    user_id: str,
    request: Request | None,
    action: str,
    per_minute_user: int,
    per_hour_user: int,
    per_minute_ip: int,
    per_hour_ip: int,
    now: datetime | None = None,
    extra_detail: dict[str, Any] | None = None,
) -> None:
    check_rate_limit(
        user_id=user_id,
        action=action,
        per_minute=int(per_minute_user),
        per_hour=int(per_hour_user),
        now=now,
        extra_detail=extra_detail,
    )

    ip_hash = ip_hash_from_request(request)
    if not ip_hash:
        return
    check_rate_limit(
        user_id=f"ip:{ip_hash[:48]}",
        action=action,
        per_minute=int(per_minute_ip),
        per_hour=int(per_hour_ip),
        now=now,
        extra_detail={**(extra_detail or {}), "scope": "ip"},
    )
