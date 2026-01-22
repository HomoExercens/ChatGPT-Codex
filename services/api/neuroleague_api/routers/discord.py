from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import DBSession
from neuroleague_api.discord_launch import (
    build_daily_post_payload,
    discord_application_id,
    discord_bot_token,
    discord_guild_id,
    discord_mode,
    discord_public_key,
    enqueue_discord_outbox,
    ensure_daily_challenge,
    process_outbox,
    public_base_url,
)
from neuroleague_api.models import DiscordOutbox


router = APIRouter(prefix="/api/discord", tags=["discord"])
ops_router = APIRouter(prefix="/api/ops/discord", tags=["ops"])


def _require_admin(x_admin_token: str | None) -> None:
    settings = Settings()
    expected = str(settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=401, detail="admin_disabled")
    if str(x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class OpsDiscordOut(BaseModel):
    mode: str
    enabled: bool
    queued: int = 0
    sent: int = 0
    failed: int = 0
    last_sent_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None


class OpsDiscordTestOut(BaseModel):
    ok: bool = True
    outbox_id: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    processed: dict[str, Any] = Field(default_factory=dict)


class OpsDiscordRegisterOut(BaseModel):
    ok: bool = True
    scope: str
    response: list[dict[str, Any]] | dict[str, Any]


@ops_router.get("", response_model=OpsDiscordOut)
def ops_status(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsDiscordOut:
    _require_admin(x_admin_token)
    settings = Settings()
    mode = discord_mode(settings)

    queued = int(
        db.scalar(
            select(func.count(DiscordOutbox.id)).where(DiscordOutbox.status == "queued")
        )
        or 0
    )
    sent = int(
        db.scalar(
            select(func.count(DiscordOutbox.id)).where(DiscordOutbox.status == "sent")
        )
        or 0
    )
    failed = int(
        db.scalar(
            select(func.count(DiscordOutbox.id)).where(DiscordOutbox.status == "failed")
        )
        or 0
    )

    last_sent_at = db.scalar(
        select(DiscordOutbox.sent_at)
        .where(DiscordOutbox.status == "sent")
        .order_by(desc(DiscordOutbox.sent_at))
        .limit(1)
    )
    last_err_row = db.scalar(
        select(DiscordOutbox)
        .where(DiscordOutbox.last_error.is_not(None))
        .order_by(desc(DiscordOutbox.created_at))
        .limit(1)
    )
    last_error = (
        str(last_err_row.last_error)[:400]
        if last_err_row and last_err_row.last_error
        else None
    )
    last_error_at = (
        last_err_row.created_at.isoformat()
        if last_err_row and last_err_row.created_at
        else None
    )

    enabled = bool(mode in {"mock", "webhook", "app"})
    return OpsDiscordOut(
        mode=str(mode),
        enabled=enabled,
        queued=queued,
        sent=sent,
        failed=failed,
        last_sent_at=last_sent_at.isoformat() if last_sent_at else None,
        last_error=last_error,
        last_error_at=last_error_at,
    )


@ops_router.post("/test_post", response_model=OpsDiscordTestOut)
def ops_test_post(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsDiscordTestOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)
    payload = build_daily_post_payload(db, now=now)
    outbox = enqueue_discord_outbox(db, kind="test_post", payload=payload, now=now)
    processed = process_outbox(db, limit=3, now=now)
    db.commit()
    row = db.get(DiscordOutbox, outbox.id)
    return OpsDiscordTestOut(
        ok=True,
        outbox_id=str(outbox.id),
        status=str(row.status if row else "queued"),
        payload=payload,
        processed=processed,
    )


def _register_commands_payload() -> list[dict[str, Any]]:
    # A single /nl command with subcommands.
    return [
        {
            "name": "nl",
            "type": 1,
            "description": "NeuroLeague shortcuts",
            "options": [
                {"type": 1, "name": "top", "description": "Top clip today"},
                {"type": 1, "name": "challenge", "description": "Daily challenge link"},
                {
                    "type": 1,
                    "name": "weekly",
                    "description": "Weekly theme / tournament link",
                },
                {
                    "type": 1,
                    "name": "build",
                    "description": "Import a build code",
                    "options": [
                        {
                            "type": 3,
                            "name": "code",
                            "description": "Build code",
                            "required": True,
                        }
                    ],
                },
            ],
        }
    ]


@ops_router.post("/register_commands", response_model=OpsDiscordRegisterOut)
def ops_register_commands(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsDiscordRegisterOut:
    _require_admin(x_admin_token)
    settings = Settings()
    if discord_mode(settings) != "app":
        raise HTTPException(status_code=400, detail="discord_mode_not_app")

    app_id = discord_application_id(settings)
    token = discord_bot_token(settings)
    if not app_id or not token:
        raise HTTPException(status_code=400, detail="missing_discord_app_config")

    guild = discord_guild_id(settings)
    payload = _register_commands_payload()
    headers = {"Authorization": f"Bot {token}"}
    if guild:
        url = (
            f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild}/commands"
        )
        scope = "guild"
    else:
        url = f"https://discord.com/api/v10/applications/{app_id}/commands"
        scope = "global"

    resp = httpx.put(url, json=payload, headers=headers, timeout=15.0)
    try:
        parsed = resp.json()
    except Exception:  # noqa: BLE001
        parsed = {"status_code": resp.status_code, "body": resp.text[:600]}
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=parsed)
    return OpsDiscordRegisterOut(ok=True, scope=scope, response=parsed)


def _verify_signature(*, request: Request, raw_body: bytes, settings: Settings) -> None:
    mode = discord_mode(settings)
    if mode == "mock":
        return
    if mode != "app":
        raise HTTPException(status_code=400, detail="discord_mode_not_app")

    sig = request.headers.get("X-Signature-Ed25519")
    ts = request.headers.get("X-Signature-Timestamp")
    if not sig or not ts:
        raise HTTPException(status_code=401, detail="missing_signature")

    pub = discord_public_key(settings)
    if not pub:
        raise HTTPException(status_code=500, detail="missing_public_key")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub))
        pk.verify(bytes.fromhex(sig), ts.encode("utf-8") + raw_body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401, detail=f"bad_signature:{str(exc)[:120]}"
        ) from None


@router.post("/interactions")
async def interactions(
    request: Request,
    db: Session = DBSession,
) -> dict[str, Any]:
    settings = Settings()
    raw = await request.body()
    _verify_signature(request=request, raw_body=raw, settings=settings)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid_json") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")

    t = int(payload.get("type") or 0)
    if t == 1:
        return {"type": 1}

    if t != 2:
        return {"type": 4, "data": {"content": "Unsupported interaction type."}}

    data = payload.get("data") or {}
    name = str(data.get("name") or "")
    opts = data.get("options") or []
    sub = ""
    sub_opts: list[dict[str, Any]] = []
    if isinstance(opts, list) and opts:
        first = opts[0]
        if isinstance(first, dict) and first.get("type") == 1:
            sub = str(first.get("name") or "")
            sub_opts = (
                first.get("options") if isinstance(first.get("options"), list) else []
            )

    base = public_base_url(settings)

    if name != "nl":
        return {"type": 4, "data": {"content": f"Unknown command: {name}"}}

    if sub == "weekly":
        return {"type": 4, "data": {"content": f"{base}/tournament"}}

    if sub == "build":
        code = ""
        for o in sub_opts:
            if isinstance(o, dict) and str(o.get("name") or "") == "code":
                code = str(o.get("value") or "")
        if not code.strip():
            return {"type": 4, "data": {"content": "Missing build code."}}
        next_path = f"/forge?import={quote(code.strip(), safe='')}"
        return {
            "type": 4,
            "data": {"content": f"{base}/start?next={quote(next_path, safe='')}"},
        }

    # Use daily challenge as a canonical deterministic pick.
    daily = ensure_daily_challenge(db)
    if sub == "challenge":
        return {
            "type": 4,
            "data": {"content": f"{base}/s/challenge/{daily.challenge_id}"},
        }

    if sub == "top":
        if daily.replay_id:
            return {
                "type": 4,
                "data": {"content": f"{base}/s/clip/{daily.replay_id}?v=1"},
            }
        return {"type": 4, "data": {"content": f"{base}/clips"}}

    return {
        "type": 4,
        "data": {
            "content": "Available: /nl top | /nl challenge | /nl weekly | /nl build <code>"
        },
    }
