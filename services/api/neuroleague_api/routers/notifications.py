from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _encode_cursor(*, created_at: datetime, notification_id: str) -> str:
    created_at = _as_aware(created_at) or datetime.fromtimestamp(0, tz=UTC)
    payload = {"t": created_at.isoformat(), "id": str(notification_id)}
    raw = orjson.dumps(payload)
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    raw = str(cursor or "").strip()
    if not raw:
        raise ValueError("empty cursor")
    pad = "=" * (-len(raw) % 4)
    data = base64.urlsafe_b64decode(raw + pad)
    obj = orjson.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("invalid cursor")
    t = obj.get("t")
    nid = obj.get("id")
    if not isinstance(t, str) or not isinstance(nid, str):
        raise ValueError("invalid cursor")
    dt = _as_aware(datetime.fromisoformat(t)) or datetime.fromtimestamp(0, tz=UTC)
    return dt, nid


def _safe_json_dict(raw: str | None) -> dict[str, Any]:
    try:
        obj = orjson.loads(raw or "{}")
    except Exception:  # noqa: BLE001
        return {}
    return obj if isinstance(obj, dict) else {}


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str | None = None
    body: str | None = None
    href: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read_at: datetime | None = None


class NotificationsOut(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None = None
    unread_count: int = 0


@router.get("", response_model=NotificationsOut)
def list_notifications(
    cursor: str | None = None,
    limit: int = 20,
    unread: bool = False,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> NotificationsOut:
    if str(user_id or "").startswith("guest_"):
        return NotificationsOut(items=[], next_cursor=None, unread_count=0)

    limit = max(1, min(50, int(limit)))

    unread_count = int(
        db.scalar(
            select(func.count(Notification.id))
            .where(Notification.user_id == user_id)
            .where(Notification.read_at.is_(None))
        )
        or 0
    )

    q = select(Notification).where(Notification.user_id == user_id)
    if unread:
        q = q.where(Notification.read_at.is_(None))

    cursor_t: datetime | None = None
    cursor_id: str | None = None
    if cursor:
        try:
            cursor_t, cursor_id = _decode_cursor(cursor)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor") from None

    if cursor_t is not None and cursor_id is not None:
        q = q.where(
            (Notification.created_at < cursor_t)
            | ((Notification.created_at == cursor_t) & (Notification.id < cursor_id))
        )

    rows = db.scalars(
        q.order_by(desc(Notification.created_at), desc(Notification.id)).limit(limit + 1)
    ).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(
            created_at=_as_aware(last.created_at) or datetime.fromtimestamp(0, tz=UTC),
            notification_id=last.id,
        )

    items: list[NotificationOut] = []
    for n in rows:
        items.append(
            NotificationOut(
                id=str(n.id),
                type=str(n.type),
                title=n.title,
                body=n.body,
                href=n.href,
                meta=_safe_json_dict(n.meta_json),
                created_at=_as_aware(n.created_at) or datetime.fromtimestamp(0, tz=UTC),
                read_at=_as_aware(n.read_at),
            )
        )

    return NotificationsOut(items=items, next_cursor=next_cursor, unread_count=unread_count)


class MarkReadResponse(BaseModel):
    ok: bool = True
    id: str
    unread_count: int = 0


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
def mark_read(
    notification_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> MarkReadResponse:
    if str(user_id or "").startswith("guest_"):
        return MarkReadResponse(ok=True, id=str(notification_id), unread_count=0)

    n = db.get(Notification, notification_id)
    if not n or str(n.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="Notification not found")

    now = datetime.now(UTC)
    if n.read_at is None:
        n.read_at = now
        db.add(n)
        db.commit()

    unread_count = int(
        db.scalar(
            select(func.count(Notification.id))
            .where(Notification.user_id == user_id)
            .where(Notification.read_at.is_(None))
        )
        or 0
    )
    return MarkReadResponse(ok=True, id=str(notification_id), unread_count=unread_count)

