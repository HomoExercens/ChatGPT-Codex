from __future__ import annotations

from datetime import UTC, datetime, timedelta

import orjson


def test_alerts_funnel_drop_cooldown(seeded_db, monkeypatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_ALERTS_ENABLED", "1")
    monkeypatch.setenv("NEUROLEAGUE_DISCORD_MODE", "mock")

    from neuroleague_api.alerts import run_alerts_check
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import AlertSent, DiscordOutbox, FunnelDaily

    now = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
    today = now.date()

    with SessionLocal() as session:
        # 7d avg=100, today=50 => triggers (drop >= 40%, min_samples satisfied).
        for i in range(1, 8):
            d = today - timedelta(days=i)
            session.merge(
                FunnelDaily(
                    date=d, funnel_name="share_v1", step="share_open", users_count=100
                )
            )
        session.merge(
            FunnelDaily(
                date=today,
                funnel_name="share_v1",
                step="share_open",
                users_count=50,
            )
        )
        session.commit()

        res1 = run_alerts_check(session, now=now)
        session.commit()

        assert res1.get("enabled") is True
        assert "funnel_drop:share_v1:share_open" in (res1.get("emitted") or [])
        assert (
            session.query(DiscordOutbox).filter(DiscordOutbox.kind == "alert").count()
            == 1
        )
        outbox = (
            session.query(DiscordOutbox)
            .filter(DiscordOutbox.kind == "alert")
            .order_by(DiscordOutbox.created_at.desc())
            .first()
        )
        assert outbox is not None
        payload = orjson.loads(outbox.payload_json or "{}")
        assert "[SEV:WARN]" in str(payload.get("content") or "")
        assert str((payload.get("neuroleague_alert") or {}).get("severity") or "") == "WARN"
        assert session.query(AlertSent).count() == 1

        res2 = run_alerts_check(session, now=now + timedelta(hours=1))
        session.commit()

        assert "funnel_drop:share_v1:share_open" not in (res2.get("emitted") or [])
        assert (
            session.query(DiscordOutbox).filter(DiscordOutbox.kind == "alert").count()
            == 1
        )


def test_alerts_5xx_spike(seeded_db, monkeypatch) -> None:
    monkeypatch.setenv("NEUROLEAGUE_ALERTS_ENABLED", "1")
    monkeypatch.setenv("NEUROLEAGUE_DISCORD_MODE", "mock")

    from neuroleague_api.alerts import run_alerts_check
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import AlertSent, DiscordOutbox, HttpErrorEvent

    now = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)

    with SessionLocal() as session:
        for i in range(5):
            session.add(
                HttpErrorEvent(
                    id=f"he_test_{i}",
                    created_at=now - timedelta(minutes=1),
                    path="/api/ready",
                    method="GET",
                    status=500,
                    request_id=f"req_test_{i}",
                )
            )
        session.commit()

        res = run_alerts_check(session, now=now)
        session.commit()

        assert res.get("enabled") is True
        assert "http_5xx_15m" in (res.get("emitted") or [])
        assert (
            session.query(DiscordOutbox).filter(DiscordOutbox.kind == "alert").count()
            >= 1
        )
        sent = (
            session.query(AlertSent)
            .filter(AlertSent.alert_key == "http_5xx_15m")
            .order_by(AlertSent.created_at.desc())
            .first()
        )
        assert sent is not None
        outbox = session.get(DiscordOutbox, str(sent.outbox_id))
        assert outbox is not None
        payload = orjson.loads(outbox.payload_json or "{}")
        assert "[SEV:CRIT]" in str(payload.get("content") or "")
        assert str((payload.get("neuroleague_alert") or {}).get("severity") or "") == "CRIT"
