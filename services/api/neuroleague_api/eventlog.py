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


def app_container_from_request(request: Request | None) -> str | None:
    """
    Optional app container hint (client-provided). Used for ops segmentation only.

    Examples:
    - "twa" (Android Trusted Web Activity)
    - "chrome"
    - "safari"
    """
    if request is None:
        return None
    raw = str(request.headers.get("x-app-container") or "").strip().lower()
    if raw in {"twa", "chrome", "safari"}:
        return raw
    return None


def _strip_quotes(s: str) -> str:
    out = str(s or "").strip()
    if out.startswith('"') and out.endswith('"') and len(out) >= 2:
        out = out[1:-1].strip()
    return out


def _uach_platform(raw: str | None) -> str | None:
    v = _strip_quotes(str(raw or ""))
    if not v:
        return None
    v_l = v.lower()
    if v_l == "android":
        return "android"
    if v_l == "ios":
        return "ios"
    # Windows/macOS/Linux/Chrome OS/... → desktop bucket.
    return "desktop"


def _uach_is_chromium(raw: str | None) -> bool:
    v = str(raw or "").lower()
    if not v:
        return False
    # Low-entropy UA-CH brands list (Sec-CH-UA). Treat Chromium-family as "chrome" container.
    return any(
        k in v
        for k in (
            "chromium",
            "google chrome",
            "microsoft edge",
            "brave",
            "opera",
            "vivaldi",
        )
    )


def _ua_platform_container(
    *,
    ua: str,
    container_hint: str | None,
    uach_platform: str | None = None,
    uach_brands: str | None = None,
) -> tuple[str, str]:
    ua_l = str(ua or "").lower()

    platform_from_ua: str | None = None
    if "android" in ua_l:
        platform_from_ua = "android"
    elif "iphone" in ua_l or "ipad" in ua_l or "ipod" in ua_l:
        platform_from_ua = "ios"

    platform = platform_from_ua or _uach_platform(uach_platform) or "desktop"

    if container_hint in {"twa", "chrome", "safari"}:
        return platform, container_hint

    # Container detection (best-effort; UA-only).
    if platform == "ios":
        if "crios" in ua_l:
            return platform, "chrome"
        if "safari" in ua_l:
            return platform, "safari"
        return platform, "unknown"

    # UA-CH brands (when UA string is reduced) → chrome bucket.
    if _uach_is_chromium(uach_brands):
        return platform, "chrome"

    if "chrome/" in ua_l or "chromium" in ua_l:
        return platform, "chrome"
    return platform, "unknown"


def _ua_segment(*, platform: str, container: str) -> str:
    p = str(platform or "").strip().lower()
    c = str(container or "").strip().lower()
    if p == "android" and c == "twa":
        return "android_twa"
    if p == "android" and c == "chrome":
        return "android_chrome"
    if p == "desktop" and c == "chrome":
        return "desktop_chrome"
    if p == "ios" and c == "safari":
        return "ios_safari"
    if p == "ios" and c == "chrome":
        return "ios_chrome"
    if p in {"android", "ios", "desktop"} and c in {"twa", "chrome", "safari"}:
        return f"{p}_{c}"
    return "unknown"


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
        # Best-effort UA segmentation for ops/experiments (do not trust client meta).
        try:
            ua = str(request.headers.get("user-agent") or "")
            container_hint = app_container_from_request(request)
            uach_platform = request.headers.get("sec-ch-ua-platform")
            uach_brands = request.headers.get("sec-ch-ua")
            platform, container = _ua_platform_container(
                ua=ua,
                container_hint=container_hint,
                uach_platform=str(uach_platform or "") if uach_platform is not None else None,
                uach_brands=str(uach_brands or "") if uach_brands is not None else None,
            )
            p["ua_platform"] = platform
            p["ua_container"] = container
            p["ua_segment"] = _ua_segment(platform=platform, container=container)
            if container_hint:
                p["ua_container_hint"] = container_hint
        except Exception:  # noqa: BLE001
            pass

    ev = Event(
        id=f"ev_{uuid4().hex}",
        user_id=user_id,
        type=str(type),
        payload_json=orjson.dumps(p).decode("utf-8"),
        created_at=now_dt,
    )
    session.add(ev)
    return ev
