from __future__ import annotations

from datetime import UTC, datetime


def test_referral_created_on_guest_start_and_credited(api_client) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Referral, UserCosmetic
    from neuroleague_api.referrals import (
        COSMETIC_REFERRER_BADGE_ID,
        COSMETIC_WELCOME_BADGE_ID,
        credit_referral_if_eligible,
    )

    guest = api_client.post(
        "/api/auth/guest", json={"ref": "user_demo", "device_id": "dev_test_1"}
    )
    assert guest.status_code == 200
    token = guest.json()["access_token"]
    me = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    guest_id = me.json()["user_id"]
    assert guest_id.startswith("guest_")

    with SessionLocal() as session:
        r = session.query(Referral).filter(Referral.new_user_id == guest_id).first()
        assert r is not None
        assert r.creator_user_id == "user_demo"
        assert r.status == "pending"

        ok = credit_referral_if_eligible(
            session,
            new_user_id=guest_id,
            match_id="m_ref_test",
            now=datetime.now(UTC),
        )
        assert ok is True
        session.commit()

    with SessionLocal() as session:
        r = session.query(Referral).filter(Referral.new_user_id == guest_id).first()
        assert r is not None
        assert r.status == "credited"
        assert r.credited_match_id == "m_ref_test"

        assert (
            session.get(
                UserCosmetic,
                {"user_id": "user_demo", "cosmetic_id": COSMETIC_REFERRER_BADGE_ID},
            )
            is not None
        )
        assert (
            session.get(
                UserCosmetic,
                {"user_id": guest_id, "cosmetic_id": COSMETIC_WELCOME_BADGE_ID},
            )
            is not None
        )


def test_referral_invalid_when_device_already_credited(api_client) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Referral
    from neuroleague_api.referrals import credit_referral_if_eligible

    # First guest: create referral and credit it.
    g1 = api_client.post(
        "/api/auth/guest", json={"ref": "user_demo", "device_id": "dev_repeat"}
    )
    assert g1.status_code == 200
    token1 = g1.json()["access_token"]
    me1 = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    gid1 = me1.json()["user_id"]

    with SessionLocal() as session:
        ok = credit_referral_if_eligible(session, new_user_id=gid1, match_id="m1")
        assert ok is True
        session.commit()

    # Second guest from same device should be marked invalid.
    g2 = api_client.post(
        "/api/auth/guest", json={"ref": "user_demo", "device_id": "dev_repeat"}
    )
    assert g2.status_code == 200
    token2 = g2.json()["access_token"]
    me2 = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
    gid2 = me2.json()["user_id"]
    assert gid2 != gid1

    with SessionLocal() as session:
        r2 = session.query(Referral).filter(Referral.new_user_id == gid2).first()
        assert r2 is not None
        assert r2.status == "invalid"
        assert r2.invalid_reason == "device_already_credited"
