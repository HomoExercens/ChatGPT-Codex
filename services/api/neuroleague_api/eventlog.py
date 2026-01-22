from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import orjson
from fastapi import Request
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.models import Event


def _hash_with_secret(*, raw: str | None) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None
    secret = Settings().auth_jwt_secret
    return hashlib.sha256(f"{value}|{secret}".encode("utf-8")).hexdigest()


def ip_hash_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    ip = getattr(getattr(request, "client", None), "host", None)
    return _hash_with_secret(raw=str(ip or ""))


def user_agent_hash_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    return _hash_with_secret(raw=str(ua or ""))


def device_id_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    value = str(request.headers.get("x-device-id") or "").strip()
    return value[:80] if value else None


def session_id_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    value = str(request.headers.get("x-session-id") or "").strip()
    return value[:80] if value else None


def utm_from_request(request: Request | None) -> dict[str, str]:
    if request is None:
        return {}
    out: dict[str, str] = {}
    for k in (
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
    ):
        v = request.query_params.get(k)
        if v:
            out[k] = str(v)[:120]
    return out


def log_event(
    session: Session,
    *,
    type: str,
    user_id: str | None,
    request: Request | None = None,
    payload: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Event:
    now_dt = now or datetime.now(UTC)
    p: dict[str, Any] = dict(payload or {})

    p.setdefault("v", 1)
    p.setdefault("user_id", user_id)
    if user_id and str(user_id).startswith("guest_"):
        p.setdefault("guest_id", user_id)

    dev = device_id_from_request(request)
    sess = session_id_from_request(request)
    if dev:
        p.setdefault("device_id", dev)
    if sess:
        p.setdefault("session_id", sess)

    ip_hash = ip_hash_from_request(request)
    ua_hash = user_agent_hash_from_request(request)
    if ip_hash:
        p.setdefault("ip_hash", ip_hash)
    if ua_hash:
        p.setdefault("user_agent_hash", ua_hash)

    if request is not None:
        try:
            p.setdefault("path", str(request.url.path))
        except Exception:  # noqa: BLE001
            pass
        utm = utm_from_request(request)
        if utm:
            p.setdefault("utm", utm)

    ev = Event(
        id=f"ev_{uuid4().hex}",
        user_id=user_id,
        type=str(type),
        payload_json=orjson.dumps(p).decode("utf-8"),
        created_at=now_dt,
    )
    session.add(ev)
    return ev
