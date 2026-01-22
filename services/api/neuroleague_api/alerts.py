from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import orjson
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.discord_launch import enqueue_discord_outbox
from neuroleague_api.models import (
    AlertSent,
    Event,
    FunnelDaily,
    HttpErrorEvent,
    RenderJob,
)
from neuroleague_api.storage_backend import get_storage_backend


ALERTS_VERSION: str = "alertsv1"
ALERT_COOLDOWN_SEC: int = 2 * 60 * 60

AlertSeverity = Literal["INFO", "WARN", "CRIT"]


@dataclass(frozen=True)
class FunnelDropRule:
    funnel_name: str
    top_step: str
    drop_threshold: float = 0.40
    min_samples: int = 30


FUNNEL_DROP_RULES: list[FunnelDropRule] = [
    FunnelDropRule(funnel_name="share_v1", top_step="share_open"),
    FunnelDropRule(funnel_name="clips_v1", top_step="clip_view"),
    FunnelDropRule(funnel_name="demo_v1", top_step="demo_run_start"),
]


def _today(now: datetime) -> date:
    return (now.astimezone(UTC)).date()


def _avg(values: list[int]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def _should_send_key(session: Session, *, alert_key: str, now: datetime) -> bool:
    last = session.scalar(
        select(AlertSent.created_at)
        .where(AlertSent.alert_key == str(alert_key))
        .order_by(desc(AlertSent.created_at))
        .limit(1)
    )
    if last is None:
        return True
    try:
        last_dt = (
            last if isinstance(last, datetime) else datetime.fromisoformat(str(last))
        )
    except Exception:  # noqa: BLE001
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (now - last_dt) >= timedelta(seconds=int(ALERT_COOLDOWN_SEC))


def _clamp_discord_content(text_in: str) -> str:
    s = str(text_in or "")
    if len(s) <= 1900:
        return s
    return s[:1890].rstrip() + "\n…"


def _alert_prefix(severity: AlertSeverity) -> str:
    return f"[NeuroLeague ALERT][SEV:{severity}]"


def _enqueue_alert(
    session: Session,
    *,
    alert_key: str,
    severity: AlertSeverity,
    summary: str,
    content: str,
    now: datetime,
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {"content": _clamp_discord_content(content)}
    meta: dict[str, Any] = {"severity": severity, "version": ALERTS_VERSION}
    if extra:
        meta.update(extra)
    payload["neuroleague_alert"] = meta

    outbox = enqueue_discord_outbox(session, kind="alert", payload=payload, now=now)
    session.add(
        AlertSent(
            id=f"as_{uuid4().hex}",
            alert_key=str(alert_key)[:120],
            outbox_id=str(outbox.id),
            summary=(f"[{severity}] {summary}" if summary else f"[{severity}]")[:240],
            payload_json=orjson.dumps(payload).decode("utf-8"),
            created_at=now,
        )
    )
    return str(outbox.id)


def _ready_check(session: Session) -> tuple[bool, str | None]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return False, f"db: {str(exc)[:160]}"
    try:
        _ = get_storage_backend().public_url(key="ops/ready.txt")
    except Exception as exc:  # noqa: BLE001
        return False, f"storage: {str(exc)[:160]}"
    return True, None


def run_alerts_check(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    settings = Settings()
    now_dt = now or datetime.now(UTC)

    if not bool(getattr(settings, "alerts_enabled", False)):
        return {"ok": True, "enabled": False, "emitted": []}

    base = str(getattr(settings, "public_base_url", "") or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:3000"

    emitted: list[str] = []
    checks: list[dict[str, Any]] = []

    # 1) Readiness
    ok, err = _ready_check(session)
    checks.append({"check": "ready", "ok": bool(ok), "error": err})
    if not ok:
        key = "ready_fail"
        if _should_send_key(session, alert_key=key, now=now_dt):
            _enqueue_alert(
                session,
                alert_key=key,
                severity="CRIT",
                summary="ready fail",
                content=f"{_alert_prefix('CRIT')} /api/ready failing\n- {err}\n- ops: {base}/ops",
                now=now_dt,
                extra={"error": err, "base_url": base},
            )
            emitted.append(key)

    # 2) Funnel drops (top-of-funnel volume)
    today = _today(now_dt)
    yday = today - timedelta(days=1)
    start_7 = today - timedelta(days=7)

    for rule in FUNNEL_DROP_RULES:
        today_val = session.scalar(
            select(FunnelDaily.users_count)
            .where(FunnelDaily.date == today)
            .where(FunnelDaily.funnel_name == rule.funnel_name)
            .where(FunnelDaily.step == rule.top_step)
        )
        today_n = int(today_val or 0)

        prev_rows = session.execute(
            select(FunnelDaily.users_count)
            .where(FunnelDaily.date >= start_7)
            .where(FunnelDaily.date <= yday)
            .where(FunnelDaily.funnel_name == rule.funnel_name)
            .where(FunnelDaily.step == rule.top_step)
            .order_by(FunnelDaily.date.asc())
        ).all()
        prev = [int(v or 0) for (v,) in prev_rows]
        avg7 = _avg(prev[-7:])

        checks.append(
            {
                "check": "funnel_drop",
                "funnel": rule.funnel_name,
                "step": rule.top_step,
                "today": today_n,
                "avg7": round(avg7, 2),
            }
        )

        if today_n < int(rule.min_samples) or avg7 < float(rule.min_samples):
            continue
        threshold = float(rule.drop_threshold)
        if avg7 <= 0.0:
            continue
        if float(today_n) >= (avg7 * (1.0 - threshold)):
            continue

        key = f"funnel_drop:{rule.funnel_name}:{rule.top_step}"
        if not _should_send_key(session, alert_key=key, now=now_dt):
            continue

        pct = (float(today_n) / float(avg7)) if avg7 > 0 else 0.0
        _enqueue_alert(
            session,
            alert_key=key,
            severity="WARN",
            summary=f"funnel drop {rule.funnel_name}",
            content=(
                f"{_alert_prefix('WARN')} Funnel drop: {rule.funnel_name}/{rule.top_step}\n"
                f"- today: {today_n}\n"
                f"- avg_7d: {avg7:.1f}\n"
                f"- ratio: {(pct * 100):.1f}% (threshold {(1.0 - threshold) * 100:.0f}%)\n"
                f"- ops: {base}/ops"
            ),
            now=now_dt,
            extra={
                "funnel": rule.funnel_name,
                "step": rule.top_step,
                "today": today_n,
                "avg7": avg7,
                "base_url": base,
            },
        )
        emitted.append(key)

    # 3) 5xx spikes (last 15m)
    cutoff_15m = now_dt - timedelta(minutes=15)
    err_5xx = int(
        session.scalar(
            select(func.count(HttpErrorEvent.id))
            .where(HttpErrorEvent.created_at >= cutoff_15m)
            .where(HttpErrorEvent.status >= 500)
        )
        or 0
    )
    checks.append({"check": "http_5xx_15m", "count": err_5xx})
    if err_5xx >= 5:
        key = "http_5xx_15m"
        if _should_send_key(session, alert_key=key, now=now_dt):
            _enqueue_alert(
                session,
                alert_key=key,
                severity="CRIT",
                summary="5xx spike",
                content=f"{_alert_prefix('CRIT')} 5xx spike (last 15m): {err_5xx}\n- ops: {base}/ops",
                now=now_dt,
                extra={"count": err_5xx, "base_url": base},
            )
            emitted.append(key)

    # 4) Render backlog
    backlog = int(
        session.scalar(
            select(func.count(RenderJob.id)).where(
                RenderJob.status.in_(["queued", "running"])
            )
        )
        or 0
    )
    checks.append({"check": "render_jobs_backlog", "count": backlog})
    if backlog >= 200:
        key = "render_jobs_backlog"
        if _should_send_key(session, alert_key=key, now=now_dt):
            _enqueue_alert(
                session,
                alert_key=key,
                severity="WARN",
                summary="render backlog",
                content=f"{_alert_prefix('WARN')} render_jobs backlog: {backlog}\n- ops: {base}/ops",
                now=now_dt,
                extra={"count": backlog, "base_url": base},
            )
            emitted.append(key)

    # Persist a lightweight audit event for Ops.
    backend = get_storage_backend()
    _ = backend  # keep side effects (init) consistent; no external calls.
    session.add(
        Event(
            id=f"ev_{uuid4().hex}",
            user_id=None,
            type="ops_alerts_check",
            payload_json=orjson.dumps(
                {"version": ALERTS_VERSION, "emitted": emitted, "checks": checks}
            ).decode("utf-8"),
            created_at=now_dt,
        )
    )

    return {"ok": True, "enabled": True, "emitted": emitted, "checks": checks}
