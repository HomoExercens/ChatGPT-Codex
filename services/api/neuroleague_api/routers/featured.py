from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import DBSession
from neuroleague_api.featured_rotation import preview_daily_featured
from neuroleague_api.models import FeaturedItem


FeaturedKind = Literal["clip", "build", "user", "challenge"]


def _require_admin(x_admin_token: str | None) -> None:
    settings = Settings()
    expected = str(settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=401, detail="admin_disabled")
    if str(x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


def _href_for_item(*, kind: str, target_id: str) -> str:
    if kind == "clip":
        return f"/s/clip/{target_id}"
    if kind == "build":
        return f"/s/build/{target_id}"
    if kind == "user":
        return f"/s/profile/{target_id}"
    if kind == "challenge":
        return f"/s/challenge/{target_id}"
    return "/home"


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _is_active(*, row: FeaturedItem, now: datetime) -> bool:
    if str(row.status or "") != "active":
        return False
    starts = _as_aware_utc(row.starts_at)
    if starts is not None and starts > now:
        return False
    ends = _as_aware_utc(row.ends_at)
    if ends is not None and ends <= now:
        return False
    return True


class FeaturedItemOut(BaseModel):
    id: str
    kind: FeaturedKind
    target_id: str
    title_override: str | None = None
    priority: int = 0
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str
    created_at: datetime
    created_by: str | None = None
    href: str


class OpsFeaturedCreateIn(BaseModel):
    kind: FeaturedKind
    target_id: str = Field(min_length=1, max_length=120)
    priority: int = 0
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    title_override: str | None = Field(default=None, max_length=120)


class OpsFeaturedUpdateIn(BaseModel):
    priority: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    title_override: str | None = Field(default=None, max_length=120)


class OpsExpireOut(BaseModel):
    ok: bool = True
    expired: int = 0


class OpsDeleteOut(BaseModel):
    ok: bool = True


router = APIRouter(prefix="/api/featured", tags=["featured"])
ops_router = APIRouter(prefix="/api/ops/featured", tags=["ops"])


def _to_out(item: FeaturedItem) -> FeaturedItemOut:
    kind = str(item.kind or "clip")
    return FeaturedItemOut(
        id=str(item.id),
        kind=kind,  # type: ignore[arg-type]
        target_id=str(item.target_id),
        title_override=item.title_override,
        priority=int(item.priority or 0),
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        status=str(item.status or "active"),
        created_at=item.created_at,
        created_by=item.created_by,
        href=_href_for_item(kind=kind, target_id=str(item.target_id)),
    )


@router.get("", response_model=list[FeaturedItemOut])
def list_featured(
    kind: FeaturedKind | None = None,
    active: bool = True,
    db: Session = DBSession,
) -> list[FeaturedItemOut]:
    now = datetime.now(UTC)
    q = select(FeaturedItem)
    if kind:
        q = q.where(FeaturedItem.kind == str(kind))
    q = q.order_by(desc(FeaturedItem.priority), desc(FeaturedItem.created_at))
    rows = db.scalars(q.limit(200)).all()
    if active:
        rows = [r for r in rows if _is_active(row=r, now=now)]
    return [_to_out(r) for r in rows]


@ops_router.get("", response_model=list[FeaturedItemOut])
def ops_list_featured(
    kind: FeaturedKind | None = None,
    active: bool = False,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> list[FeaturedItemOut]:
    _require_admin(x_admin_token)
    return list_featured(kind=kind, active=bool(active), db=db)


class FeaturedPreviewItemOut(BaseModel):
    kind: FeaturedKind
    target_id: str | None = None
    source: str
    featured_id: str | None = None
    priority: int | None = None
    href: str | None = None


class FeaturedPreviewOut(BaseModel):
    day: str
    starts_at: datetime
    ends_at: datetime
    items: list[FeaturedPreviewItemOut] = Field(default_factory=list)


@ops_router.get("/preview", response_model=FeaturedPreviewOut)
def ops_preview_featured(
    offset_days: int = 1,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> FeaturedPreviewOut:
    _require_admin(x_admin_token)
    offset_days = max(0, min(7, int(offset_days)))
    now = datetime.now(UTC) + timedelta(days=offset_days)
    res = preview_daily_featured(db, now=now)

    items: list[FeaturedPreviewItemOut] = []
    for it in (res.get("items") or []):
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind") or "clip")
        target_id = it.get("target_id")
        target_id_s = str(target_id) if isinstance(target_id, str) and target_id else None
        items.append(
            FeaturedPreviewItemOut(
                kind=kind,  # type: ignore[arg-type]
                target_id=target_id_s,
                source=str(it.get("source") or ""),
                featured_id=str(it.get("featured_id") or "") or None,
                priority=int(it.get("priority") or 0) if it.get("priority") is not None else None,
                href=_href_for_item(kind=kind, target_id=target_id_s) if target_id_s else None,
            )
        )

    return FeaturedPreviewOut(
        day=str(res.get("day") or ""),
        starts_at=res.get("starts_at") or datetime.now(UTC),
        ends_at=res.get("ends_at") or datetime.now(UTC),
        items=items,
    )


@ops_router.post("", response_model=FeaturedItemOut)
def ops_create_featured(
    payload: OpsFeaturedCreateIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> FeaturedItemOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)

    starts_at = payload.starts_at
    ends_at = payload.ends_at
    if starts_at is not None and starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    if ends_at is not None and ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=UTC)
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise HTTPException(status_code=400, detail="ends_at_must_be_after_starts_at")

    item = FeaturedItem(
        id=f"fi_{uuid4().hex}",
        kind=str(payload.kind),
        target_id=str(payload.target_id),
        title_override=payload.title_override,
        priority=int(payload.priority or 0),
        starts_at=starts_at,
        ends_at=ends_at,
        status="active",
        created_at=now,
        created_by="ops",
    )
    db.add(item)
    db.commit()
    return _to_out(item)


@ops_router.delete("/{featured_id}", response_model=OpsDeleteOut)
def ops_delete_featured(
    featured_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsDeleteOut:
    _require_admin(x_admin_token)
    row = db.get(FeaturedItem, featured_id)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    db.delete(row)
    db.commit()
    return OpsDeleteOut(ok=True)


@ops_router.post("/{featured_id}/update", response_model=FeaturedItemOut)
def ops_update_featured(
    featured_id: str,
    payload: OpsFeaturedUpdateIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> FeaturedItemOut:
    _require_admin(x_admin_token)
    row = db.get(FeaturedItem, featured_id)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")

    if payload.priority is not None:
        row.priority = int(payload.priority)
    if payload.starts_at is not None or "starts_at" in payload.model_fields_set:
        starts = payload.starts_at
        if starts is not None and starts.tzinfo is None:
            starts = starts.replace(tzinfo=UTC)
        row.starts_at = starts
    if payload.ends_at is not None or "ends_at" in payload.model_fields_set:
        ends = payload.ends_at
        if ends is not None and ends.tzinfo is None:
            ends = ends.replace(tzinfo=UTC)
        row.ends_at = ends
    if "title_override" in payload.model_fields_set:
        row.title_override = payload.title_override

    starts = _as_aware_utc(row.starts_at)
    ends = _as_aware_utc(row.ends_at)
    if starts is not None and ends is not None and ends <= starts:
        raise HTTPException(status_code=400, detail="ends_at_must_be_after_starts_at")

    db.add(row)
    db.commit()
    return _to_out(row)


@ops_router.post("/expire", response_model=OpsExpireOut)
def ops_expire_featured(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsExpireOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)
    res = db.execute(
        update(FeaturedItem)
        .where(FeaturedItem.status == "active")
        .where(FeaturedItem.ends_at.is_not(None))
        .where(FeaturedItem.ends_at <= now)
        .values(status="expired")
    )
    db.commit()
    expired = int(getattr(res, "rowcount", 0) or 0)
    return OpsExpireOut(ok=True, expired=expired)
