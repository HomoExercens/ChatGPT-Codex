from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import orjson
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.models import Cosmetic, Event, Referral, User, UserCosmetic


REFERRAL_STATUS_PENDING: Literal["pending"] = "pending"
REFERRAL_STATUS_CREDITED: Literal["credited"] = "credited"
REFERRAL_STATUS_INVALID: Literal["invalid"] = "invalid"

COSMETIC_REFERRER_BADGE_ID = "badge_referral_ambassador"
COSMETIC_WELCOME_BADGE_ID = "badge_welcome_referral"


def _hash_ip(ip: str | None) -> str | None:
    raw = str(ip or "").strip()
    if not raw:
        return None
    secret = Settings().auth_jwt_secret
    return hashlib.sha256(f"{raw}|{secret}".encode("utf-8")).hexdigest()


def _ensure_badge(session: Session, *, badge_id: str, name: str, now: datetime) -> None:
    if session.get(Cosmetic, badge_id) is None:
        session.add(
            Cosmetic(
                id=badge_id,
                kind="badge",
                name=name,
                asset_path=None,
                created_at=now,
            )
        )


def create_referral_on_guest_start(
    session: Session,
    *,
    creator_user_id: str | None,
    new_user_id: str,
    device_id: str | None,
    client_ip: str | None,
    now: datetime | None = None,
) -> Referral | None:
    ref = str(creator_user_id or "").strip()
    if not ref:
        return None
    if ref == new_user_id:
        return None

    if session.get(User, ref) is None:
        return None

    now_dt = now or datetime.now(UTC)
    ip_hash = _hash_ip(client_ip)

    status = REFERRAL_STATUS_PENDING
    reason: str | None = None

    if device_id:
        already = session.scalar(
            select(Referral)
            .where(Referral.device_id == device_id)
            .where(Referral.status == REFERRAL_STATUS_CREDITED)
            .limit(1)
        )
        if already:
            status = REFERRAL_STATUS_INVALID
            reason = "device_already_credited"

    if status == REFERRAL_STATUS_PENDING and ip_hash:
        settings = Settings()
        limit = int(getattr(settings, "referral_ip_credit_limit_per_day", 3) or 3)
        if limit > 0:
            since = now_dt - timedelta(days=1)
            credited_count = int(
                session.scalar(
                    select(func.count(Referral.id))
                    .where(Referral.ip_hash == ip_hash)
                    .where(Referral.status == REFERRAL_STATUS_CREDITED)
                    .where(Referral.credited_at.is_not(None))
                    .where(Referral.credited_at >= since)
                )
                or 0
            )
            if credited_count >= limit:
                status = REFERRAL_STATUS_INVALID
                reason = "ip_credit_limit"

    referral = Referral(
        id=f"ref_{uuid4().hex}",
        creator_user_id=ref,
        new_user_id=new_user_id,
        status=status,
        invalid_reason=reason,
        device_id=device_id,
        ip_hash=ip_hash,
        created_at=now_dt,
        credited_at=None,
        credited_match_id=None,
    )
    session.add(referral)

    if status != REFERRAL_STATUS_PENDING:
        session.add(
            Event(
                id=f"ev_{uuid4().hex}",
                user_id=new_user_id,
                type="anti_abuse_flag",
                payload_json=orjson.dumps(
                    {
                        "reason": "referral_invalid",
                        "invalid_reason": reason,
                        "ref": ref,
                        "device_id": device_id,
                    }
                ).decode("utf-8"),
                created_at=now_dt,
            )
        )

    return referral


def credit_referral_if_eligible(
    session: Session,
    *,
    new_user_id: str,
    match_id: str,
    now: datetime | None = None,
) -> bool:
    now_dt = now or datetime.now(UTC)
    referral = session.scalar(
        select(Referral)
        .where(Referral.new_user_id == new_user_id)
        .order_by(desc(Referral.created_at))
        .limit(1)
    )
    if not referral:
        return False
    if referral.status != REFERRAL_STATUS_PENDING:
        return False

    creator = str(referral.creator_user_id or "").strip()
    if not creator or creator == new_user_id:
        referral.status = REFERRAL_STATUS_INVALID
        referral.invalid_reason = "invalid_creator"
        return False

    if session.get(User, creator) is None:
        referral.status = REFERRAL_STATUS_INVALID
        referral.invalid_reason = "missing_creator"
        return False

    _ensure_badge(
        session,
        badge_id=COSMETIC_REFERRER_BADGE_ID,
        name="Referral Ambassador",
        now=now_dt,
    )
    _ensure_badge(
        session,
        badge_id=COSMETIC_WELCOME_BADGE_ID,
        name="Welcome (Referred)",
        now=now_dt,
    )

    if (
        session.get(
            UserCosmetic,
            {"user_id": creator, "cosmetic_id": COSMETIC_REFERRER_BADGE_ID},
        )
        is None
    ):
        session.add(
            UserCosmetic(
                user_id=creator,
                cosmetic_id=COSMETIC_REFERRER_BADGE_ID,
                earned_at=now_dt,
                source="referral_credit",
            )
        )
    if (
        session.get(
            UserCosmetic,
            {"user_id": new_user_id, "cosmetic_id": COSMETIC_WELCOME_BADGE_ID},
        )
        is None
    ):
        session.add(
            UserCosmetic(
                user_id=new_user_id,
                cosmetic_id=COSMETIC_WELCOME_BADGE_ID,
                earned_at=now_dt,
                source="referral_welcome",
            )
        )

    referral.status = REFERRAL_STATUS_CREDITED
    referral.credited_at = now_dt
    referral.credited_match_id = match_id

    session.add(
        Event(
            id=f"ev_{uuid4().hex}",
            user_id=creator,
            type="referral_credited",
            payload_json=orjson.dumps(
                {"new_user_id": new_user_id, "match_id": match_id}
            ).decode("utf-8"),
            created_at=now_dt,
        )
    )
    return True
