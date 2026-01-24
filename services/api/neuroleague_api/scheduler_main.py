from __future__ import annotations

import argparse
import signal
import time
from datetime import UTC, datetime
from uuid import uuid4

import orjson

from neuroleague_api.balance_report import compute_balance_report
from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal
from neuroleague_api.growth_metrics import rollup_growth_metrics
from neuroleague_api.models import Event, FeaturedItem
from neuroleague_api.ops_cleanup import cleanup_render_jobs
from neuroleague_api.storage_backend import get_storage_backend, guess_content_type

from sqlalchemy import update


def _balance_md(payload: dict) -> str:
    lines: list[str] = [
        "# Balance Report (Scheduler)",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ruleset_version: `{payload.get('ruleset_version')}`",
        f"- queue_type: `{payload.get('queue_type')}`",
        f"- low_confidence_min_samples: `{payload.get('low_confidence_min_samples')}`",
        "",
    ]
    modes = payload.get("modes") or {}
    for mode in ("1v1", "team"):
        m = modes.get(mode) or {}
        overall = m.get("overall") or {}
        lines.append(f"## Mode: {mode}")
        lines.append(
            f"- matches_total: `{int(m.get('matches_total') or 0)}` · "
            f"wr={(float(overall.get('winrate') or 0.0) * 100):.1f}% · "
            f"avg_elo={float(overall.get('avg_elo_delta') or 0.0):+.1f}"
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_once(*, days: int = 30, queue_type: str = "ranked") -> dict[str, object]:
    settings = Settings()
    backend = get_storage_backend()
    now = datetime.now(UTC)

    report: dict | None = None
    with SessionLocal() as session:
        from neuroleague_api.locks import advisory_lock

        with advisory_lock(session, name="scheduler_ops_rollup") as acquired:
            if acquired:
                rollup_res = rollup_growth_metrics(session, days=int(days))
                session.add(
                    Event(
                        id=f"ev_{uuid4().hex}",
                        user_id=None,
                        type="ops_metrics_rollup",
                        payload_json=orjson.dumps(
                            {
                                "days": int(days),
                                "start": rollup_res.start_date.isoformat(),
                                "end": rollup_res.end_date.isoformat(),
                            }
                        ).decode("utf-8"),
                        created_at=now,
                    )
                )

                report = compute_balance_report(
                    session,
                    ruleset_version=settings.ruleset_version,
                    queue_type=str(queue_type),
                    generated_at=now.isoformat(),
                    limit_matches=50_000,
                )
                session.add(
                    Event(
                        id=f"ev_{uuid4().hex}",
                        user_id=None,
                        type="ops_balance_report",
                        payload_json=orjson.dumps(
                            {"queue_type": str(queue_type)}
                        ).decode("utf-8"),
                        created_at=now,
                    )
                )

                # Guardrailed bandit auto-weighting (best-effort).
                try:
                    from neuroleague_api.experiments import bandit_update_for_experiment

                    bandit_results = {
                        "clip_len_v1": bandit_update_for_experiment(
                            session, experiment_key="clip_len_v1", now=now
                        ),
                        "captions_v2": bandit_update_for_experiment(
                            session, experiment_key="captions_v2", now=now
                        ),
                    }
                    session.add(
                        Event(
                            id=f"ev_{uuid4().hex}",
                            user_id=None,
                            type="ops_bandit_update",
                            payload_json=orjson.dumps(
                                {"results": bandit_results}
                            ).decode("utf-8"),
                            created_at=now,
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass
                session.commit()

    # Daily maintenance: expire scheduled featured items (safe to run any time).
    try:
        with SessionLocal() as session:
            from neuroleague_api.locks import advisory_lock

            with advisory_lock(session, name="scheduler_featured_daily") as acquired:
                if not acquired:
                    raise RuntimeError("lock_busy")
            session.execute(
                update(FeaturedItem)
                .where(FeaturedItem.status == "active")
                .where(FeaturedItem.ends_at.is_not(None))
                .where(FeaturedItem.ends_at <= now)
                .values(status="expired")
            )
            session.commit()
            from neuroleague_api.featured_rotation import ensure_daily_featured

            ensure_daily_featured(session, now=now)
    except Exception:  # noqa: BLE001
        pass

    # Daily hero clips auto-curation (best-effort; ops override can pin/exclude).
    try:
        with SessionLocal() as session:
            from neuroleague_api.hero_clips import recompute_hero_clips
            from neuroleague_api.locks import advisory_lock

            with advisory_lock(session, name="scheduler_hero_clips_daily") as acquired:
                if acquired:
                    recompute_hero_clips(session, now=now, backend=backend)
    except Exception:  # noqa: BLE001
        pass

    # Discord daily loop (optional): ensure daily challenge + enqueue daily post + drain outbox.
    try:
        with SessionLocal() as session:
            from neuroleague_api.locks import advisory_lock

            with advisory_lock(session, name="scheduler_discord_daily") as acquired:
                if not acquired:
                    raise RuntimeError("lock_busy")
            from neuroleague_api.discord_launch import (
                build_daily_post_payload,
                enqueue_discord_outbox,
                process_outbox,
                should_send_daily_post,
            )

            from neuroleague_api.discord_launch import ensure_daily_challenge

            ensure_daily_challenge(session, now=now)
            if should_send_daily_post(session, now=now):
                payload = build_daily_post_payload(session, now=now)
                enqueue_discord_outbox(
                    session, kind="daily_post", payload=payload, now=now
                )
            process_outbox(session, limit=10, now=now)
            session.commit()
    except Exception:  # noqa: BLE001
        pass

    if report is None:
        return {"ok": True, "generated_at": now.isoformat(), "days": int(days), "skipped": True}

    stamp = now.strftime("%Y%m%d")
    json_bytes = orjson.dumps(report, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    md_bytes = _balance_md(report).encode("utf-8")

    backend.put_bytes(
        key=f"ops/balance_report_{stamp}.json",
        data=json_bytes,
        content_type=guess_content_type("balance_report.json"),
    )
    backend.put_bytes(
        key="ops/balance_report_latest.json",
        data=json_bytes,
        content_type=guess_content_type("balance_report.json"),
    )
    backend.put_bytes(
        key=f"ops/balance_report_{stamp}.md",
        data=md_bytes,
        content_type="text/markdown; charset=utf-8",
    )
    backend.put_bytes(
        key="ops/balance_report_latest.md",
        data=md_bytes,
        content_type="text/markdown; charset=utf-8",
    )

    retention_out: dict[str, int] | None = None
    if bool(getattr(settings, "artifacts_retention_enabled", False)):
        from datetime import timedelta

        keep_days = int(getattr(settings, "artifacts_retention_days", 14) or 14)
        keep_shared_days = int(
            getattr(settings, "artifacts_retention_keep_shared_days", 7) or 0
        )
        with SessionLocal() as session:
            from neuroleague_api.locks import advisory_lock

            with advisory_lock(session, name="scheduler_retention_cleanup") as acquired:
                if not acquired:
                    raise RuntimeError("lock_busy")
            retention_out = cleanup_render_jobs(
                session,
                now=now,
                done_ttl=timedelta(days=keep_days),
                orphan_ttl=timedelta(hours=12),
                purge_artifacts=True,
                keep_shared_ttl=timedelta(days=keep_shared_days)
                if keep_shared_days > 0
                else None,
                delete_limit=2000,
            )
            session.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=None,
                    type="ops_artifacts_retention",
                    payload_json=orjson.dumps(
                        {
                            "days": keep_days,
                            "keep_shared_days": keep_shared_days,
                            **retention_out,
                        }
                    ).decode("utf-8"),
                    created_at=now,
                )
            )
            session.commit()
        backend.put_bytes(
            key="ops/retention_latest.json",
            data=orjson.dumps(
                retention_out, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
            ),
            content_type="application/json",
        )

    try:
        with SessionLocal() as session:
            from neuroleague_api.locks import advisory_lock
            from neuroleague_api.metrics import cleanup_http_error_events

            with advisory_lock(session, name="scheduler_http_errors_ttl") as acquired:
                if acquired:
                    cleanup_http_error_events(session, keep_days=3, now=now)
    except Exception:  # noqa: BLE001
        pass

    # Alerts (optional): funnel drops, error spikes, backlog.
    try:
        with SessionLocal() as session:
            from neuroleague_api.alerts import run_alerts_check
            from neuroleague_api.locks import advisory_lock

            with advisory_lock(session, name="scheduler_alerts_check") as acquired:
                if acquired:
                    run_alerts_check(session, now=now)
                    session.commit()
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "generated_at": now.isoformat(), "days": int(days)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="NeuroLeague ops scheduler (metrics + balance reports)."
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument(
        "--days", type=int, default=30, help="Metrics rollup range (days)."
    )
    parser.add_argument(
        "--queue-type", default="ranked", choices=["ranked", "tournament"]
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if not bool(settings.scheduler_enabled):
        print("[scheduler] disabled (NEUROLEAGUE_SCHEDULER_ENABLED=false)")
        return 0

    stop = {"flag": False}

    def _handle(_sig, _frame) -> None:  # noqa: ANN001
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    interval_min = int(getattr(settings, "scheduler_interval_minutes", 60 * 24) or 1440)
    interval_sec = max(60, interval_min * 60)

    while True:
        res = run_once(days=int(args.days), queue_type=str(args.queue_type))
        print(f"[scheduler] ok: {orjson.dumps(res).decode('utf-8')}")
        if args.once or stop["flag"]:
            return 0
        time.sleep(interval_sec)


if __name__ == "__main__":
    raise SystemExit(main())
