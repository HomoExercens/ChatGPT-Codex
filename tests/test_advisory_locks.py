from __future__ import annotations


def test_advisory_lock_key_is_stable_and_distinct() -> None:
    from neuroleague_api.locks import advisory_lock_key

    a1 = advisory_lock_key(name="scheduler_daily")
    a2 = advisory_lock_key(name="scheduler_daily")
    b = advisory_lock_key(name="scheduler_other")

    assert isinstance(a1, int)
    assert a1 == a2
    assert a1 != b


def test_try_advisory_lock_is_noop_on_sqlite(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.locks import try_advisory_lock

    with SessionLocal() as session:
        assert try_advisory_lock(session, name="noop_test") is True

