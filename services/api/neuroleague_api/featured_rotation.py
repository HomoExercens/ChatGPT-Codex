from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.models import Blueprint, FeaturedItem, Match, Replay, User


FeaturedKind = Literal["clip", "build", "user", "challenge"]

KST = ZoneInfo("Asia/Seoul")


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


def _kst_day(now: datetime) -> tuple[str, datetime, datetime]:
    now_dt = _as_aware_utc(now) or datetime.now(UTC)
    now_kst = now_dt.astimezone(KST)
    day_id = now_kst.date().strftime("%Y%m%d")
    start_kst = datetime(now_kst.year, now_kst.month, now_kst.day, tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return day_id, start_kst.astimezone(UTC), end_kst.astimezone(UTC)


def _pick_deterministic(candidates: list[str], *, salt: str) -> str | None:
    xs = [str(x).strip() for x in candidates if str(x).strip()]
    xs = sorted(set(xs))
    if not xs:
        return None
    digest = hashlib.sha256(salt.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "little", signed=False) % len(xs)
    return xs[idx]


def _candidate_clip_ids(session: Session, *, limit: int = 120) -> list[str]:
    rows = session.execute(
        select(Replay.id)
        .join(Match, Match.id == Replay.match_id)
        .where(Match.status == "done")
        .order_by(desc(Match.finished_at), desc(Match.created_at), Replay.id.asc())
        .limit(int(limit))
    ).all()
    return [str(rid) for (rid,) in rows if rid]


def _candidate_build_ids(session: Session, *, limit: int = 200) -> list[str]:
    rows = session.execute(
        select(Blueprint.id)
        .where(Blueprint.status == "submitted")
        .where(~Blueprint.user_id.like("bot_%"))
        .order_by(desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id.asc())
        .limit(int(limit))
    ).all()
    return [str(bid) for (bid,) in rows if bid]


def _candidate_user_ids(session: Session, *, limit: int = 200) -> list[str]:
    rows = session.execute(
        select(User.id)
        .where(User.is_guest.is_(False))
        .order_by(User.id.asc())
        .limit(int(limit))
    ).all()
    return [str(uid) for (uid,) in rows if uid]


def ensure_daily_featured(
    session: Session,
    *,
    now: datetime | None = None,
    kinds: list[FeaturedKind] | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(UTC)
    day_key, starts_at, ends_at = _kst_day(now_dt)

    wanted = kinds or ["clip", "build", "user"]
    created = 0
    updated = 0
    skipped: dict[str, str] = {}

    for kind in wanted:
        kind_s = str(kind)
        ops_override = session.scalar(
            select(FeaturedItem.id)
            .where(FeaturedItem.kind == kind_s)
            .where(FeaturedItem.created_by == "ops")
            .where(FeaturedItem.status == "active")
            .where((FeaturedItem.starts_at.is_(None)) | (FeaturedItem.starts_at <= now_dt))
            .where((FeaturedItem.ends_at.is_(None)) | (FeaturedItem.ends_at > now_dt))
            .limit(1)
        )
        if ops_override:
            skipped[kind_s] = "ops_override"
            continue

        if kind_s == "clip":
            target_id = _pick_deterministic(
                _candidate_clip_ids(session), salt=f"{day_key}|clip"
            )
            priority = 120
        elif kind_s == "build":
            target_id = _pick_deterministic(
                _candidate_build_ids(session), salt=f"{day_key}|build"
            )
            priority = 110
        elif kind_s == "user":
            target_id = _pick_deterministic(
                _candidate_user_ids(session), salt=f"{day_key}|user"
            )
            priority = 100
        else:
            skipped[kind_s] = "unsupported"
            continue

        if not target_id:
            skipped[kind_s] = "no_candidates"
            continue

        sched_id = f"fi_sched_{kind_s}_{day_key}"
        row = session.get(FeaturedItem, sched_id)
        if row is None:
            session.add(
                FeaturedItem(
                    id=sched_id,
                    kind=kind_s,
                    target_id=str(target_id),
                    title_override=None,
                    priority=int(priority),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    status="active",
                    created_at=now_dt,
                    created_by="scheduler",
                )
            )
            created += 1
            continue

        changed = False
        if str(row.kind or "") != kind_s:
            row.kind = kind_s
            changed = True
        if str(row.target_id or "") != str(target_id):
            row.target_id = str(target_id)
            changed = True
        if int(row.priority or 0) != int(priority):
            row.priority = int(priority)
            changed = True
        if _as_aware_utc(row.starts_at) != starts_at:
            row.starts_at = starts_at
            changed = True
        if _as_aware_utc(row.ends_at) != ends_at:
            row.ends_at = ends_at
            changed = True
        if str(row.status or "") != "active":
            row.status = "active"
            changed = True
        if str(row.created_by or "") != "scheduler":
            row.created_by = "scheduler"
            changed = True

        if changed:
            session.add(row)
            updated += 1
        else:
            skipped[kind_s] = "up_to_date"

    session.commit()
    return {
        "ok": True,
        "day": day_key,
        "created": int(created),
        "updated": int(updated),
        "skipped": skipped,
    }


def preview_daily_featured(
    session: Session,
    *,
    now: datetime | None = None,
    kinds: list[FeaturedKind] | None = None,
) -> dict[str, Any]:
    now_dt = now or datetime.now(UTC)
    day_key, starts_at, ends_at = _kst_day(now_dt)

    wanted = kinds or ["clip", "build", "user"]
    items: list[dict[str, Any]] = []

    for kind in wanted:
        kind_s = str(kind)

        ops_override = session.scalar(
            select(FeaturedItem)
            .where(FeaturedItem.kind == kind_s)
            .where(FeaturedItem.created_by == "ops")
            .where(FeaturedItem.status == "active")
            .where((FeaturedItem.starts_at.is_(None)) | (FeaturedItem.starts_at <= now_dt))
            .where((FeaturedItem.ends_at.is_(None)) | (FeaturedItem.ends_at > now_dt))
            .order_by(desc(FeaturedItem.priority), desc(FeaturedItem.created_at))
            .limit(1)
        )
        if ops_override:
            items.append(
                {
                    "kind": kind_s,
                    "target_id": str(ops_override.target_id),
                    "source": "ops_override",
                    "featured_id": str(ops_override.id),
                    "priority": int(ops_override.priority or 0),
                }
            )
            continue

        if kind_s == "clip":
            target_id = _pick_deterministic(
                _candidate_clip_ids(session), salt=f"{day_key}|clip"
            )
            priority = 120
        elif kind_s == "build":
            target_id = _pick_deterministic(
                _candidate_build_ids(session), salt=f"{day_key}|build"
            )
            priority = 110
        elif kind_s == "user":
            target_id = _pick_deterministic(
                _candidate_user_ids(session), salt=f"{day_key}|user"
            )
            priority = 100
        else:
            items.append(
                {
                    "kind": kind_s,
                    "target_id": None,
                    "source": "unsupported",
                    "featured_id": None,
                    "priority": None,
                }
            )
            continue

        items.append(
            {
                "kind": kind_s,
                "target_id": str(target_id) if target_id else None,
                "source": "scheduler_preview" if target_id else "no_candidates",
                "featured_id": f"fi_sched_{kind_s}_{day_key}",
                "priority": int(priority),
            }
        )

    return {
        "ok": True,
        "day": day_key,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "items": items,
    }
