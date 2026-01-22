from __future__ import annotations

import os
from datetime import UTC, datetime


def test_daily_challenge_deterministic_and_payload_shape(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.discord_launch import (
        build_daily_post_payload,
        ensure_daily_challenge,
    )
    from neuroleague_api.models import Challenge, FeaturedItem
    from sqlalchemy import select

    os.environ["NEUROLEAGUE_DISCORD_MODE"] = "mock"

    fixed = datetime(2026, 1, 2, 0, 15, tzinfo=UTC)
    with SessionLocal() as session:
        first = ensure_daily_challenge(session, now=fixed)
        session.commit()
        second = ensure_daily_challenge(session, now=fixed)
        session.commit()

        assert first.challenge_id == second.challenge_id

        ch = session.get(Challenge, first.challenge_id)
        assert ch is not None
        assert ch.kind == "clip"

        feat = session.scalar(
            select(FeaturedItem)
            .where(FeaturedItem.kind == "challenge")
            .where(FeaturedItem.target_id == first.challenge_id)
            .limit(1)
        )
        assert feat is not None

        payload1 = build_daily_post_payload(session, now=fixed)
        payload2 = build_daily_post_payload(session, now=fixed)
        assert payload1 == payload2
        assert isinstance(payload1.get("content"), str)
        assert isinstance(payload1.get("embeds"), list)
        assert isinstance(payload1.get("components"), list)


def test_discord_mock_enqueue_and_process_outbox(seeded_db, monkeypatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_DISCORD_MODE", "mock")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.discord_launch import (
        build_daily_post_payload,
        enqueue_discord_outbox,
        process_outbox,
    )
    from neuroleague_api.models import DiscordOutbox

    fixed = datetime(2026, 1, 2, 0, 15, tzinfo=UTC)
    with SessionLocal() as session:
        payload = build_daily_post_payload(session, now=fixed)
        assert isinstance(payload.get("content"), str)
        assert len(str(payload.get("content") or "")) < 2000

        row = enqueue_discord_outbox(
            session, kind="daily_post", payload=payload, now=fixed
        )
        session.commit()

        res = process_outbox(session, limit=10, now=fixed)
        session.commit()
        assert bool(res.get("ok")) is True
        assert int(res.get("sent") or 0) >= 1

        refreshed = session.get(DiscordOutbox, row.id)
        assert refreshed is not None
        assert str(refreshed.status) == "sent"
