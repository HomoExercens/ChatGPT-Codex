from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException

from neuroleague_api.rate_limit import check_rate_limit_dual


class _DummyClient:
    host = "203.0.113.10"


class _DummyRequest:
    client = _DummyClient()


def test_rate_limit_dual_enforces_ip_scope_across_users() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    action = "test_rate_limit_dual_ip_scope_v1"

    check_rate_limit_dual(
        user_id="user_a",
        request=_DummyRequest(),  # type: ignore[arg-type]
        action=action,
        per_minute_user=999,
        per_hour_user=999,
        per_minute_ip=1,
        per_hour_ip=999,
        now=now,
    )

    try:
        check_rate_limit_dual(
            user_id="user_b",
            request=_DummyRequest(),  # type: ignore[arg-type]
            action=action,
            per_minute_user=999,
            per_hour_user=999,
            per_minute_ip=1,
            per_hour_ip=999,
            now=now,
        )
    except HTTPException as exc:
        assert exc.status_code == 429
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("retry_after_sec")
        assert exc.detail.get("scope") == "ip"
        assert (exc.headers or {}).get("Retry-After")
    else:
        raise AssertionError("expected ip-based rate limit to trigger")

