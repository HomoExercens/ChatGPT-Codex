from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from neuroleague_api.core.security import decode_token
from neuroleague_api.db import SessionLocal


def get_db() -> Session:
    with SessionLocal() as session:
        yield session


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid token") from e
    return str(payload.get("sub"))


CurrentUserId = Depends(get_current_user_id)
DBSession = Depends(get_db)
