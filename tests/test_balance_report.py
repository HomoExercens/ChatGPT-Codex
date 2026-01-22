from __future__ import annotations

from neuroleague_api.balance_report import compute_balance_report
from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal


def test_balance_report_deterministic(seeded_db) -> None:
    settings = Settings()
    with SessionLocal() as session:
        r1 = compute_balance_report(
            session,
            ruleset_version=settings.ruleset_version,
            queue_type="ranked",
            generated_at="2026-01-01T00:00:00+00:00",
            limit_matches=500,
        )
        r2 = compute_balance_report(
            session,
            ruleset_version=settings.ruleset_version,
            queue_type="ranked",
            generated_at="2026-01-01T00:00:00+00:00",
            limit_matches=500,
        )

    assert r1 == r2
    assert "modes" in r1
    assert "1v1" in r1["modes"]
    assert "team" in r1["modes"]
    assert int(r1["modes"]["team"]["matches_total"] or 0) >= 0
