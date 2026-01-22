from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from neuroleague_api.core.config import Settings


def create_access_token(*, subject: str, is_guest: bool) -> str:
    settings = Settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": settings.auth_jwt_issuer,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.auth_jwt_exp_minutes)).timestamp()
        ),
        "guest": bool(is_guest),
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    settings = Settings()
    return jwt.decode(
        token,
        settings.auth_jwt_secret,
        algorithms=["HS256"],
        issuer=settings.auth_jwt_issuer,
    )
