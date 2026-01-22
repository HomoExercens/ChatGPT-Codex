from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import secrets
from urllib.parse import quote, urlencode
from uuid import uuid4

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import jwt
import orjson

from neuroleague_api.core.config import Settings
from neuroleague_api.core.security import create_access_token
from neuroleague_api.core.security import decode_token as _decode_access_token
from neuroleague_api.deps import DBSession, CurrentUserId
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import (
    Blueprint,
    ClipLike,
    Event,
    Rating,
    Referral,
    TrainingRun,
    User,
    UserCosmetic,
    UserHiddenClip,
    Wallet,
)
from neuroleague_api.referrals import create_referral_on_guest_start

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str


class MeResponse(BaseModel):
    user_id: str
    display_name: str
    is_guest: bool
    avatar_url: str | None = None
    discord_connected: bool = False


class GuestStartRequest(BaseModel):
    ref: str | None = Field(default=None, max_length=80)
    device_id: str | None = Field(default=None, max_length=80)
    method: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=64)
    next: str | None = Field(default=None, max_length=2000)
    utm: dict[str, str] = Field(default_factory=dict)
    lenv: str | None = Field(default=None, max_length=16)
    cv: str | None = Field(default=None, max_length=32)
    ctpl: str | None = Field(default=None, max_length=64)


@router.post("/guest", response_model=AuthResponse)
def auth_guest(
    request: Request,
    req: GuestStartRequest | None = Body(default=None),
    db: Session = DBSession,
) -> AuthResponse:
    user_id = f"guest_{uuid4().hex}"
    user = User(
        id=user_id,
        username=None,
        display_name="Guest Researcher",
        is_guest=True,
        created_at=datetime.now(UTC),
    )
    db.add(user)
    db.add(Wallet(user_id=user.id, tokens_balance=500))
    db.add(
        Rating(
            user_id=user.id,
            mode="1v1",
            elo=1000,
            games_played=0,
            updated_at=datetime.now(UTC),
        )
    )
    db.add(
        Rating(
            user_id=user.id,
            mode="team",
            elo=1000,
            games_played=0,
            updated_at=datetime.now(UTC),
        )
    )
    create_referral_on_guest_start(
        db,
        creator_user_id=req.ref if req else None,
        new_user_id=user.id,
        device_id=req.device_id if req else None,
        client_ip=getattr(getattr(request, "client", None), "host", None),
    )
    try:
        method = str(getattr(req, "method", None) or "").strip() if req else ""
        if not method:
            method = "deep_link" if (req and req.ref) else "direct"

        src = str(getattr(req, "source", None) or "").strip() if req else ""
        next_path = (
            _safe_next_path(str(getattr(req, "next", None) or "")) if req else ""
        )
        utm = getattr(req, "utm", None) if req else None
        utm_out: dict[str, str] = utm if isinstance(utm, dict) else {}
        lenv = str(getattr(req, "lenv", None) or "").strip() if req else ""
        cv = str(getattr(req, "cv", None) or "").strip() if req else ""
        ctpl = str(getattr(req, "ctpl", None) or "").strip() if req else ""
        variants = {}
        if lenv:
            variants["clip_len_v1"] = lenv[:16]
        if ctpl:
            variants["captions_v2"] = ctpl[:64]

        if src:
            log_event(
                db,
                type="share_cta_click",
                user_id=user.id,
                request=request,
                payload={
                    "source": src,
                    "ref": req.ref if req else None,
                    "device_id": req.device_id if req else None,
                    "next": next_path or None,
                    "utm": utm_out,
                    "variants": variants,
                    "captions_version": cv[:32] if cv else None,
                },
            )
            log_event(
                db,
                type="start_click",
                user_id=user.id,
                request=request,
                payload={
                    "source": src,
                    "ref": req.ref if req else None,
                    "device_id": req.device_id if req else None,
                    "next": next_path or None,
                    "utm": utm_out,
                    "variants": variants,
                    "captions_version": cv[:32] if cv else None,
                },
            )
            if src.endswith("_qr"):
                log_event(
                    db,
                    type="qr_scanned_click",
                    user_id=user.id,
                    request=request,
                    payload={
                        "source": src,
                        "ref": req.ref if req else None,
                        "device_id": req.device_id if req else None,
                        "next": next_path or None,
                        "utm": utm_out,
                        "variants": variants,
                        "captions_version": cv[:32] if cv else None,
                    },
                )
        log_event(
            db,
            type="guest_start_success",
            user_id=user.id,
            request=request,
            payload={
                "method": method,
                "ref": req.ref if req else None,
                "device_id": req.device_id if req else None,
                "source": src or None,
                "next": next_path or None,
                "utm": utm_out,
                "variants": variants,
                "captions_version": cv[:32] if cv else None,
            },
        )
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return AuthResponse(
        access_token=create_access_token(subject=user.id, is_guest=True)
    )


@router.post("/login", response_model=AuthResponse)
def auth_login(req: LoginRequest, db: Session = DBSession) -> AuthResponse:
    user = db.scalar(select(User).where(User.username == req.username))
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user (try username: demo)")
    return AuthResponse(
        access_token=create_access_token(subject=user.id, is_guest=user.is_guest)
    )


@router.get("/me", response_model=MeResponse)
def auth_me(user_id: str = CurrentUserId, db: Session = DBSession) -> MeResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        user_id=user.id,
        display_name=user.display_name,
        is_guest=user.is_guest,
        avatar_url=user.avatar_url,
        discord_connected=bool(user.discord_id),
    )


def _safe_next_path(next_path: str | None) -> str:
    raw = str(next_path or "").strip()
    if not raw:
        return "/home"
    if raw.startswith("//") or "://" in raw:
        return "/home"
    if not raw.startswith("/"):
        return "/home"
    if "\n" in raw or "\r" in raw:
        return "/home"
    return raw


def _abs_base(request: Request) -> str:
    settings = Settings()
    if settings.public_base_url:
        return str(settings.public_base_url).rstrip("/")
    return str(request.base_url).rstrip("/")


def _encode_discord_state(*, next_path: str, link_user_id: str | None) -> str:
    settings = Settings()
    now = datetime.now(UTC)
    payload = {
        "iss": settings.auth_jwt_issuer,
        "typ": "discord_oauth_state",
        "iat": int(now.timestamp()),
        "exp": int((now.timestamp()) + 10 * 60),
        "next": next_path,
        "link_user_id": link_user_id,
        "nonce": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")


def _decode_discord_state(state: str) -> dict:
    settings = Settings()
    payload = jwt.decode(
        state,
        settings.auth_jwt_secret,
        algorithms=["HS256"],
        issuer=settings.auth_jwt_issuer,
    )
    if payload.get("typ") != "discord_oauth_state":
        raise ValueError("invalid state type")
    return payload


def _avatar_url(*, discord_id: str, avatar_hash: str | None) -> str | None:
    if not avatar_hash:
        return None
    return f"https://cdn.discordapp.com/avatars/{quote(discord_id)}/{quote(avatar_hash)}.png?size=128"


def _merge_guest_into(
    db: Session,
    *,
    guest_user_id: str,
    target_user_id: str,
    now: datetime,
) -> None:
    if guest_user_id == target_user_id:
        return
    guest = db.get(User, guest_user_id)
    if not guest or not guest.is_guest:
        return
    target = db.get(User, target_user_id)
    if not target:
        return

    # Transfer blueprint/trainings ownership.
    db.query(Blueprint).filter(Blueprint.user_id == guest_user_id).update(
        {"user_id": target_user_id}
    )
    db.query(TrainingRun).filter(TrainingRun.user_id == guest_user_id).update(
        {"user_id": target_user_id}
    )

    # Transfer wallet tokens (best-effort).
    guest_wallet = db.get(Wallet, guest_user_id)
    target_wallet = db.get(Wallet, target_user_id)
    if guest_wallet:
        if not target_wallet:
            target_wallet = Wallet(user_id=target_user_id, tokens_balance=0)
            db.add(target_wallet)
        target_wallet.tokens_balance = int(target_wallet.tokens_balance or 0) + int(
            guest_wallet.tokens_balance or 0
        )

    # Transfer cosmetics (dedupe by PK).
    guest_cos = (
        db.query(UserCosmetic).filter(UserCosmetic.user_id == guest_user_id).all()
    )
    for uc in guest_cos:
        if (
            db.get(
                UserCosmetic, {"user_id": target_user_id, "cosmetic_id": uc.cosmetic_id}
            )
            is None
        ):
            db.add(
                UserCosmetic(
                    user_id=target_user_id,
                    cosmetic_id=uc.cosmetic_id,
                    earned_at=uc.earned_at,
                    source=uc.source,
                )
            )

    # Transfer clip likes / hidden clips (dedupe).
    guest_likes = db.query(ClipLike).filter(ClipLike.user_id == guest_user_id).all()
    for like in guest_likes:
        if (
            db.get(ClipLike, {"user_id": target_user_id, "replay_id": like.replay_id})
            is None
        ):
            db.add(
                ClipLike(
                    user_id=target_user_id,
                    replay_id=like.replay_id,
                    created_at=like.created_at,
                )
            )

    guest_hidden = (
        db.query(UserHiddenClip).filter(UserHiddenClip.user_id == guest_user_id).all()
    )
    for hid in guest_hidden:
        if (
            db.get(
                UserHiddenClip, {"user_id": target_user_id, "replay_id": hid.replay_id}
            )
            is None
        ):
            db.add(
                UserHiddenClip(
                    user_id=target_user_id,
                    replay_id=hid.replay_id,
                    created_at=hid.created_at,
                )
            )

    # Transfer referral attribution if possible (unique per new_user_id).
    ref = db.scalar(
        select(Referral).where(Referral.new_user_id == guest_user_id).limit(1)
    )
    if (
        ref
        and db.scalar(
            select(Referral).where(Referral.new_user_id == target_user_id).limit(1)
        )
        is None
    ):
        ref.new_user_id = target_user_id
        db.add(ref)

    # Mark merge for ops visibility.
    db.add(
        Event(
            id=f"ev_{uuid4().hex}",
            user_id=target_user_id,
            type="auth_merge",
            payload_json=orjson.dumps(
                {
                    "from_user_id": guest_user_id,
                    "to_user_id": target_user_id,
                    "provider": "discord",
                }
            ).decode("utf-8"),
            created_at=now,
        )
    )

    # Finally delete guest.
    db.delete(guest)


class DiscordStartOut(BaseModel):
    authorize_url: str


@router.get("/discord/start", response_model=DiscordStartOut | None)
def discord_start(
    request: Request,
    next: str | None = None,  # noqa: A002
    format: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = DBSession,
) -> DiscordStartOut | RedirectResponse:
    settings = Settings()
    next_path = _safe_next_path(next)

    link_user_id: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        try:
            payload = _decode_access_token(authorization.split(" ", 1)[1].strip())
            link_user_id = str(payload.get("sub") or "") or None
        except Exception:  # noqa: BLE001
            link_user_id = None

    state = _encode_discord_state(next_path=next_path, link_user_id=link_user_id)

    base = _abs_base(request)
    redirect_uri = f"{base}/api/auth/discord/callback"

    # Mock mode (local / E2E): skip external dependency.
    if settings.discord_oauth_mock or not settings.discord_client_id:
        cb = f"{redirect_uri}?{urlencode({'code': 'mock', 'state': state})}"
        if str(format or "").lower() == "json":
            return DiscordStartOut(authorize_url=cb)
        return RedirectResponse(url=cb, status_code=307)

    authorize_params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    }
    url = f"https://discord.com/oauth2/authorize?{urlencode(authorize_params)}"

    try:
        log_event(
            db,
            type="auth_discord_start",
            user_id=link_user_id,
            request=request,
            payload={"next": next_path},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    if str(format or "").lower() == "json":
        return DiscordStartOut(authorize_url=url)
    return RedirectResponse(url=url, status_code=307)


class DiscordCallbackOut(AuthResponse):
    user_id: str
    display_name: str
    merged_from_guest: bool = False


@router.get("/discord/callback", response_model=None)
def discord_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    format: str | None = None,
    mock_id: str | None = None,
    db: Session = DBSession,
) -> object:
    if error:
        raise HTTPException(status_code=400, detail=str(error)[:200])
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code/state")

    try:
        st = _decode_discord_state(state)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid state") from exc

    settings = Settings()
    next_path = _safe_next_path(str(st.get("next") or "/home"))
    link_user_id = str(st.get("link_user_id") or "").strip() or None

    base = _abs_base(request)
    redirect_uri = f"{base}/api/auth/discord/callback"

    discord_id: str
    display_name: str
    avatar_url: str | None

    if settings.discord_oauth_mock or code == "mock" or not settings.discord_client_id:
        mid = str(mock_id or "test").strip() or "test"
        discord_id = f"mock_{hashlib.sha256(mid.encode('utf-8')).hexdigest()[:12]}"
        display_name = "Discord Researcher"
        avatar_url = None
    else:
        if not settings.discord_client_secret:
            raise HTTPException(status_code=500, detail="discord_oauth_not_configured")

        import httpx

        token_resp = httpx.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="discord_token_exchange_failed")
        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="discord_token_missing")

        me_resp = httpx.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        if me_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="discord_profile_failed")
        me = me_resp.json()
        discord_id = str(me.get("id") or "").strip()
        if not discord_id:
            raise HTTPException(status_code=400, detail="discord_id_missing")
        display_name = str(
            me.get("global_name") or me.get("username") or "Discord Researcher"
        )
        avatar_url = _avatar_url(discord_id=discord_id, avatar_hash=me.get("avatar"))

    now = datetime.now(UTC)
    merged_from_guest = False

    existing = db.scalar(select(User).where(User.discord_id == discord_id).limit(1))
    link_user = db.get(User, link_user_id) if link_user_id else None

    if existing and link_user and existing.id != link_user.id:
        if bool(link_user.is_guest):
            _merge_guest_into(
                db, guest_user_id=link_user.id, target_user_id=existing.id, now=now
            )
            merged_from_guest = True
            link_user = None
        else:
            raise HTTPException(
                status_code=409, detail="discord_account_already_linked"
            )

    user: User | None = existing
    if not user:
        if link_user:
            user = link_user
        else:
            uid = f"user_{uuid4().hex}"
            user = User(
                id=uid,
                username=None,
                display_name=display_name,
                is_guest=False,
                discord_id=None,
                avatar_url=None,
                created_at=now,
            )
            db.add(user)
            db.add(Wallet(user_id=user.id, tokens_balance=500))
            db.add(
                Rating(
                    user_id=user.id,
                    mode="1v1",
                    elo=1000,
                    games_played=0,
                    updated_at=now,
                )
            )
            db.add(
                Rating(
                    user_id=user.id,
                    mode="team",
                    elo=1000,
                    games_played=0,
                    updated_at=now,
                )
            )

    user.discord_id = discord_id
    user.avatar_url = avatar_url
    user.display_name = display_name
    user.is_guest = False
    db.add(user)
    db.commit()

    try:
        log_event(
            db,
            type="auth_discord_success",
            user_id=user.id,
            request=request,
            payload={"merged_from_guest": merged_from_guest},
            now=now,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    token = create_access_token(subject=user.id, is_guest=False)

    if str(format or "").lower() == "json":
        return DiscordCallbackOut(
            access_token=token,
            token_type="bearer",
            user_id=user.id,
            display_name=user.display_name,
            merged_from_guest=merged_from_guest,
        )

    # Same-origin (Vite proxy / nginx / deploy): store token in localStorage then navigate.
    html_out = f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/></head>
  <body>
    <script>
      try {{
        localStorage.setItem('neuroleague.token', {orjson.dumps(token).decode("utf-8")});
      }} catch (e) {{}}
      window.location.replace({orjson.dumps(next_path).decode("utf-8")});
    </script>
    <noscript>Login succeeded. Open the app.</noscript>
  </body>
</html>"""
    return HTMLResponse(content=html_out)
