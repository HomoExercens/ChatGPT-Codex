from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def test_featured_rotation_creates_daily_items(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.featured_rotation import ensure_daily_featured
    from neuroleague_api.models import Blueprint, FeaturedItem, Match, Replay, User

    now = datetime(3000, 1, 2, 12, 0, tzinfo=UTC)
    with SessionLocal() as session:
        res = ensure_daily_featured(session, now=now)
        assert bool(res.get("ok")) is True
        assert str(res.get("day")) == "30000102"

        clip = session.get(FeaturedItem, "fi_sched_clip_30000102")
        assert clip is not None
        assert str(clip.kind) == "clip"
        assert str(clip.created_by or "") == "scheduler"
        assert int(clip.priority or 0) == 120
        assert _aware_utc(clip.starts_at) == datetime(3000, 1, 1, 15, 0, tzinfo=UTC)
        assert _aware_utc(clip.ends_at) == datetime(3000, 1, 2, 15, 0, tzinfo=UTC)
        replay = session.get(Replay, str(clip.target_id))
        assert replay is not None
        match = session.get(Match, str(replay.match_id))
        assert match is not None
        assert str(match.status) == "done"

        res2 = ensure_daily_featured(session, now=now)
        assert bool(res2.get("ok")) is True
        clip2 = session.get(FeaturedItem, "fi_sched_clip_30000102")
        assert clip2 is not None
        assert str(clip2.target_id) == str(clip.target_id)

        build = session.get(FeaturedItem, "fi_sched_build_30000102")
        assert build is not None
        assert str(build.kind) == "build"
        assert str(build.created_by or "") == "scheduler"
        assert int(build.priority or 0) == 110
        bp = session.get(Blueprint, str(build.target_id))
        assert bp is not None
        assert str(bp.status) == "submitted"
        assert not str(bp.user_id or "").startswith("bot_")
        build2 = session.get(FeaturedItem, "fi_sched_build_30000102")
        assert build2 is not None
        assert str(build2.target_id) == str(build.target_id)

        user = session.get(FeaturedItem, "fi_sched_user_30000102")
        assert user is not None
        assert str(user.kind) == "user"
        assert str(user.created_by or "") == "scheduler"
        assert int(user.priority or 0) == 100
        u = session.get(User, str(user.target_id))
        assert u is not None
        assert bool(u.is_guest) is False
        user2 = session.get(FeaturedItem, "fi_sched_user_30000102")
        assert user2 is not None
        assert str(user2.target_id) == str(user.target_id)


def test_featured_rotation_respects_ops_override(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.featured_rotation import ensure_daily_featured
    from neuroleague_api.models import FeaturedItem

    now = datetime(3000, 1, 3, 12, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            FeaturedItem(
                id="fi_ops_override_clip_30000103",
                kind="clip",
                target_id="r_test_seed",
                title_override="Override",
                priority=9999,
                starts_at=now,
                ends_at=now + timedelta(days=1),
                status="active",
                created_at=now,
                created_by="ops",
            )
        )
        session.commit()

        res = ensure_daily_featured(session, now=now)
        assert bool(res.get("ok")) is True
        assert str(res.get("day")) == "30000103"
        skipped = res.get("skipped") or {}
        assert skipped.get("clip") == "ops_override"

        clip = session.get(FeaturedItem, "fi_sched_clip_30000103")
        assert clip is None

        build = session.get(FeaturedItem, "fi_sched_build_30000103")
        user = session.get(FeaturedItem, "fi_sched_user_30000103")
        assert build is not None
        assert user is not None


def test_featured_preview_respects_ops_override(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.featured_rotation import preview_daily_featured
    from neuroleague_api.models import FeaturedItem

    now = datetime(3000, 1, 4, 12, 0, tzinfo=UTC)
    with SessionLocal() as session:
        session.add(
            FeaturedItem(
                id="fi_ops_override_clip_preview_30000104",
                kind="clip",
                target_id="r_test_seed",
                title_override="Override",
                priority=9999,
                starts_at=now,
                ends_at=now + timedelta(days=1),
                status="active",
                created_at=now,
                created_by="ops",
            )
        )
        session.commit()

        res = preview_daily_featured(session, now=now, kinds=["clip"])
        assert bool(res.get("ok")) is True
        assert str(res.get("day")) == "30000104"
        items = res.get("items") or []
        assert items and items[0].get("source") == "ops_override"
        assert items[0].get("target_id") == "r_test_seed"
