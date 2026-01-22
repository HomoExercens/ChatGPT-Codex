from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Event, Follow, User, UserHiddenClip


router = APIRouter(prefix="/api/feed", tags=["feed"])


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _encode_cursor(*, created_at: datetime, event_id: str) -> str:
    created_at = _as_aware(created_at) or datetime.fromtimestamp(0, tz=UTC)
    payload = {"t": created_at.isoformat(), "id": event_id}
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
    eid = obj.get("id")
    if not isinstance(t, str) or not isinstance(eid, str):
        raise ValueError("invalid cursor")
    dt = datetime.fromisoformat(t)
    dt = _as_aware(dt) or datetime.fromtimestamp(0, tz=UTC)
    return dt, eid


class ActivityActorOut(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None = None


class ActivityItemOut(BaseModel):
    id: str
    type: str
    created_at: datetime
    actor: ActivityActorOut
    payload: dict[str, Any] = Field(default_factory=dict)
    href: str | None = None


class ActivityFeedOut(BaseModel):
    items: list[ActivityItemOut]
    next_cursor: str | None = None


_ALLOWED_TYPES: set[str] = {
    "ranked_done",
    "tournament_done",
    "blueprint_submit",
    "clip_share",
    "clip_completion",
    "challenge_done",
}


def _href_for_event(
    *, event_type: str, actor_id: str, payload: dict[str, Any]
) -> str | None:
    if event_type in {"ranked_done", "tournament_done", "challenge_done"}:
        mid = str(payload.get("match_id") or "").strip()
        if mid:
            return f"/replay/{mid}"
        return None
    if event_type == "blueprint_submit":
        mode = str(payload.get("mode") or "1v1")
        return f"/profile/{actor_id}?mode={mode}"
    if event_type.startswith("clip_"):
        mid = str(payload.get("match_id") or "").strip()
        if mid:
            return f"/replay/{mid}"
        return None
    return f"/profile/{actor_id}"


@router.get("/activity", response_model=ActivityFeedOut)
def activity(
    limit: int = Query(default=30, ge=1, le=50),
    cursor: str | None = None,
    _viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ActivityFeedOut:
    followee_ids = db.scalars(
        select(Follow.followee_user_id).where(
            Follow.follower_user_id == _viewer_user_id
        )
    ).all()
    followee_ids = [str(x) for x in followee_ids if x]
    if not followee_ids:
        return ActivityFeedOut(items=[], next_cursor=None)

    hidden_replays = set(
        db.scalars(
            select(UserHiddenClip.replay_id).where(
                UserHiddenClip.user_id == _viewer_user_id
            )
        ).all()
    )

    cursor_t: datetime | None = None
    cursor_id: str | None = None
    if cursor:
        try:
            cursor_t, cursor_id = _decode_cursor(cursor)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid cursor") from None

    q = (
        select(Event)
        .where(Event.user_id.in_(followee_ids))
        .where(Event.type.in_(sorted(_ALLOWED_TYPES)))
        .order_by(desc(Event.created_at), desc(Event.id))
    )
    if cursor_t is not None and cursor_id is not None:
        q = q.where(
            (Event.created_at < cursor_t)
            | ((Event.created_at == cursor_t) & (Event.id < cursor_id))
        )

    rows = db.scalars(q.limit(int(limit) * 2)).all()
    if not rows:
        return ActivityFeedOut(items=[], next_cursor=None)

    user_ids = sorted({str(r.user_id) for r in rows if r.user_id})
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    user_by_id: dict[str, User] = {u.id: u for u in users}

    items: list[ActivityItemOut] = []
    for r in rows:
        if len(items) >= int(limit):
            break
        uid = str(r.user_id or "")
        actor = user_by_id.get(uid)
        if not actor:
            continue
        payload: dict[str, Any] = {}
        try:
            parsed = orjson.loads((r.payload_json or "{}").encode("utf-8"))
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:  # noqa: BLE001
            payload = {}

        # Respect viewer hide list for clip-related events.
        if hidden_replays and str(r.type).startswith("clip_"):
            rid = str(payload.get("replay_id") or "").strip()
            if rid and rid in hidden_replays:
                continue

        href = _href_for_event(event_type=str(r.type), actor_id=uid, payload=payload)
        items.append(
            ActivityItemOut(
                id=r.id,
                type=str(r.type),
                created_at=_as_aware(r.created_at) or datetime.fromtimestamp(0, tz=UTC),
                actor=ActivityActorOut(
                    user_id=uid,
                    display_name=str(actor.display_name),
                    avatar_url=actor.avatar_url,
                ),
                payload=payload,
                href=href,
            )
        )

    next_cursor = None
    if items:
        last = items[-1]
        next_cursor = _encode_cursor(created_at=last.created_at, event_id=last.id)
    return ActivityFeedOut(items=items, next_cursor=next_cursor)
