from __future__ import annotations

import contextlib
import hashlib
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session


def advisory_lock_key(*, name: str) -> int:
    raw = f"neuroleague:{str(name)}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _is_postgres(session: Session) -> bool:
    try:
        bind = session.get_bind()
        return bool(getattr(getattr(bind, "dialect", None), "name", "") == "postgresql")
    except Exception:  # noqa: BLE001
        return False


def try_advisory_lock(session: Session, *, name: str) -> bool:
    if not _is_postgres(session):
        return True
    key = advisory_lock_key(name=name)
    try:
        got = session.execute(
            text("SELECT pg_try_advisory_lock(:k) AS locked"), {"k": key}
        ).scalar()
        return bool(got)
    except Exception:  # noqa: BLE001
        return False


def unlock_advisory_lock(session: Session, *, name: str) -> None:
    if not _is_postgres(session):
        return
    key = advisory_lock_key(name=name)
    try:
        session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
        session.commit()
    except Exception:  # noqa: BLE001
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass


@contextlib.contextmanager
def advisory_lock(session: Session, *, name: str) -> Iterator[bool]:
    acquired = try_advisory_lock(session, name=name)
    try:
        yield acquired
    finally:
        if acquired:
            unlock_advisory_lock(session, name=name)

