from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import orjson
from sqlalchemy import select


def test_featured_sorting_and_expire(api_client) -> None:
    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"
    headers = {"X-Admin-Token": "admintest"}

    now = datetime.now(UTC)
    created = api_client.post(
        "/api/ops/featured",
        headers=headers,
        json={
            "kind": "clip",
            "target_id": "r_test_seed",
            "priority": 0,
            "starts_at": None,
            "ends_at": (now + timedelta(hours=1)).isoformat(),
            "title_override": "Low",
        },
    )
    assert created.status_code == 200
    created2 = api_client.post(
        "/api/ops/featured",
        headers=headers,
        json={
            "kind": "clip",
            "target_id": "r_test_seed",
            "priority": 10,
            "starts_at": None,
            "ends_at": (now + timedelta(hours=2)).isoformat(),
            "title_override": "High",
        },
    )
    assert created2.status_code == 200

    public = api_client.get("/api/featured?kind=clip&active=true")
    assert public.status_code == 200
    items = public.json()
    assert isinstance(items, list)
    assert items[0]["priority"] >= items[-1]["priority"]
    assert items[0]["title_override"] == "High"

    # Expire one item and verify it's marked expired.
    expired = api_client.post(
        "/api/ops/featured",
        headers=headers,
        json={
            "kind": "clip",
            "target_id": "r_test_seed",
            "priority": 5,
            "starts_at": None,
            "ends_at": (now - timedelta(seconds=1)).isoformat(),
            "title_override": "Should Expire",
        },
    )
    assert expired.status_code == 200

    res = api_client.post("/api/ops/featured/expire", headers=headers)
    assert res.status_code == 200

    ops_all = api_client.get(
        "/api/ops/featured?kind=clip&active=false", headers=headers
    )
    assert ops_all.status_code == 200
    all_items = ops_all.json()
    assert any(i["status"] == "expired" for i in all_items)

    preview = api_client.get("/api/ops/featured/preview?offset_days=1", headers=headers)
    assert preview.status_code == 200
    j = preview.json()
    assert "items" in j and isinstance(j["items"], list)


def test_quests_period_kst_and_idempotency(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import (
        Event,
        Quest,
        QuestAssignment,
        QuestEventApplied,
        User,
    )
    from neuroleague_api.quests_engine import (
        apply_event_to_quests,
        kst_today_key,
        kst_week_key,
    )

    now_utc = datetime(2026, 1, 1, 14, 59, tzinfo=UTC)  # 23:59 KST
    assert kst_today_key(now_utc=now_utc) == "2026-01-01"
    assert (
        kst_today_key(now_utc=datetime(2026, 1, 1, 15, 0, tzinfo=UTC)) == "2026-01-02"
    )

    os.environ["NEUROLEAGUE_ADMIN_TOKEN"] = "admintest"

    with SessionLocal() as session:
        user = session.get(User, "user_demo")
        assert user is not None

        # Minimal quest set (daily+weekly) for a deterministic apply.
        session.add_all(
            [
                Quest(
                    id="q_daily",
                    cadence="daily",
                    key="watch_1",
                    title="Watch 1 clip",
                    description="",
                    goal_count=1,
                    event_type="clip_completion",
                    filters_json="{}",
                    reward_cosmetic_id="badge_quest_daily_watch_1",
                    reward_amount=1,
                    active_from=None,
                    active_to=None,
                    created_at=datetime.now(UTC),
                ),
                Quest(
                    id="q_weekly",
                    cadence="weekly",
                    key="share_3",
                    title="Share 3",
                    description="",
                    goal_count=3,
                    event_type="clip_completion",
                    filters_json="{}",
                    reward_cosmetic_id="badge_quest_weekly_share_3",
                    reward_amount=1,
                    active_from=None,
                    active_to=None,
                    created_at=datetime.now(UTC),
                ),
            ]
        )
        session.commit()

        ev = Event(
            id="ev_test_1",
            user_id=user.id,
            type="clip_completion",
            payload_json=orjson.dumps({"source": "test"}).decode("utf-8"),
            created_at=now_utc,
        )
        session.add(ev)
        session.commit()

        res1 = apply_event_to_quests(session, event=ev)
        session.commit()
        res2 = apply_event_to_quests(session, event=ev)
        session.commit()

        assert res1.daily_period_key == "2026-01-01"
        assert res1.weekly_period_key == kst_week_key(now_utc=now_utc)
        assert res2.applied == 0

        assigns = session.scalars(select(QuestAssignment)).all()
        assert len(assigns) == 2
        assert all(int(a.progress_count) == 1 for a in assigns)

        applied = session.scalars(select(QuestEventApplied)).all()
        assert len(applied) == 2


def test_daily_quest_filters_match_done_queue_type(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Event, Quest, QuestAssignment, User
    from neuroleague_api.quests_engine import apply_event_to_quests

    now_utc = datetime(2026, 1, 2, 1, 0, tzinfo=UTC)

    with SessionLocal() as session:
        user = session.get(User, "user_demo")
        assert user is not None

        session.add(
            Quest(
                id="q_daily_beat_this_3",
                cadence="daily",
                key="beat_this_3",
                title="Beat This x3",
                description="",
                goal_count=3,
                event_type="match_done",
                filters_json=orjson.dumps({"queue_type": {"eq": "challenge"}}).decode("utf-8"),
                reward_cosmetic_id="badge_quest_daily_beat_this_3",
                reward_amount=1,
                active_from=None,
                active_to=None,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

        ev_ranked = Event(
            id="ev_match_done_ranked",
            user_id=user.id,
            type="match_done",
            payload_json=orjson.dumps({"queue_type": "ranked"}).decode("utf-8"),
            created_at=now_utc,
        )
        session.add(ev_ranked)
        session.commit()
        res_ranked = apply_event_to_quests(session, event=ev_ranked)
        session.commit()
        assert res_ranked.applied == 0

        ev_ch1 = Event(
            id="ev_match_done_challenge_1",
            user_id=user.id,
            type="match_done",
            payload_json=orjson.dumps({"queue_type": "challenge"}).decode("utf-8"),
            created_at=now_utc,
        )
        session.add(ev_ch1)
        session.commit()
        res_ch1 = apply_event_to_quests(session, event=ev_ch1)
        session.commit()
        assert res_ch1.applied == 1

        ev_ch2 = Event(
            id="ev_match_done_challenge_2",
            user_id=user.id,
            type="match_done",
            payload_json=orjson.dumps({"queue_type": "challenge"}).decode("utf-8"),
            created_at=now_utc,
        )
        session.add(ev_ch2)
        session.commit()
        res_ch2 = apply_event_to_quests(session, event=ev_ch2)
        session.commit()
        assert res_ch2.applied == 1

        a = session.scalar(select(QuestAssignment).where(QuestAssignment.quest_id == "q_daily_beat_this_3").limit(1))
        assert a is not None
        assert int(a.progress_count or 0) == 2
