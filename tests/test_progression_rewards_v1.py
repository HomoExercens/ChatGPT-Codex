from __future__ import annotations

from datetime import UTC, datetime


def test_streak_advances_and_resets(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import UserProgress
    from neuroleague_api.progression import apply_quest_claim_rewards

    user_id = "user_demo"
    now1 = datetime(2026, 1, 1, 0, 30, 0, tzinfo=UTC)
    now2 = datetime(2026, 1, 2, 0, 30, 0, tzinfo=UTC)
    now4 = datetime(2026, 1, 4, 0, 30, 0, tzinfo=UTC)

    with SessionLocal() as session:
        r1 = apply_quest_claim_rewards(
            session,
            user_id=user_id,
            cadence="daily",
            quest_key="beat_this_3",
            now=now1,
        )
        session.commit()
        p = session.get(UserProgress, user_id)
        assert p is not None
        assert int(p.streak_days or 0) == 1
        assert int(p.quests_claimed_total or 0) == 1
        assert int(r1.streak_days) == 1

        r2 = apply_quest_claim_rewards(
            session,
            user_id=user_id,
            cadence="daily",
            quest_key="beat_this_3",
            now=now2,
        )
        session.commit()
        p2 = session.get(UserProgress, user_id)
        assert p2 is not None
        assert int(p2.streak_days or 0) == 2
        assert int(p2.quests_claimed_total or 0) == 2
        assert bool(r2.streak_extended) is True

        r3 = apply_quest_claim_rewards(
            session,
            user_id=user_id,
            cadence="daily",
            quest_key="beat_this_3",
            now=now4,
        )
        session.commit()
        p3 = session.get(UserProgress, user_id)
        assert p3 is not None
        assert int(p3.streak_days or 0) == 1
        assert int(p3.quests_claimed_total or 0) == 3
        assert bool(r3.streak_extended) is True

