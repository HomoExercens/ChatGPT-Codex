from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import re
import statistics
from typing import Any

import orjson
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


def _dt_aware(value: datetime) -> datetime:
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=UTC)
    return value


def _safe_payload(payload_json: str | None) -> dict[str, Any]:
    try:
        obj = orjson.loads(payload_json or "{}")
    except Exception:  # noqa: BLE001
        return {}
    return obj if isinstance(obj, dict) else {}


def _subject_key(*, user_id: str | None, payload: dict[str, Any]) -> str | None:
    if user_id:
        return f"u:{str(user_id)}"
    dev = payload.get("device_id")
    if isinstance(dev, str) and dev.strip():
        return f"d:{dev.strip()[:80]}"
    ip_hash = payload.get("ip_hash")
    ua_hash = payload.get("user_agent_hash")
    if isinstance(ip_hash, str) and isinstance(ua_hash, str) and ip_hash and ua_hash:
        return f"a:{ip_hash[:24]}:{ua_hash[:24]}"
    if isinstance(ip_hash, str) and ip_hash:
        return f"ip:{ip_hash[:32]}"
    return None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    try:
        return float(statistics.median(values))
    except Exception:  # noqa: BLE001
        xs = sorted(values)
        mid = len(xs) // 2
        if len(xs) % 2 == 1:
            return float(xs[mid])
        return float(xs[mid - 1] + xs[mid]) / 2.0


def _pct(num: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return float(num) / float(denom)


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = float(seconds)
    if s < 0:
        return "—"
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{(s / 60.0):.1f}m"
    return f"{(s / 3600.0):.1f}h"


@dataclass
class _PlaytestActor:
    opened_at: datetime | None = None
    completed_at: datetime | None = None
    step_at: dict[int, datetime] | None = None

    def ensure(self) -> dict[int, datetime]:
        if self.step_at is None:
            self.step_at = {}
        return self.step_at


def _load_demo_replay_id(*, root_dir: Path) -> str | None:
    local = root_dir / "artifacts" / "ops" / "demo_ids.json"
    try:
        if local.exists():
            obj = orjson.loads(local.read_bytes())
            if isinstance(obj, dict):
                rid = str(obj.get("clip_replay_id") or "").strip()
                return rid or None
    except Exception:  # noqa: BLE001
        pass
    return None


_UVICORN_LINE_RE = re.compile(
    r"\"(?P<method>[A-Z]+) (?P<path>[^ ]+) HTTP/[0-9.]+\" (?P<status>[0-9]{3})"
)


def _scan_logs_for_status_counts(*, root_dir: Path, status: int) -> dict[str, int]:
    # Best-effort: local dev tooling writes logs under artifacts/*.log.
    # In real deploys you may not have file logs; in that case this returns {}.
    artifacts = root_dir / "artifacts"
    if not artifacts.exists():
        return {}

    candidates: list[Path] = []
    for p in (
        artifacts / "api_debug.log",
        artifacts / "preview",
        artifacts / "handoff",
    ):
        if p.is_file():
            candidates.append(p)
        elif p.is_dir():
            candidates.extend(sorted(p.glob("*.log")))

    counts: Counter[str] = Counter()
    wanted = str(int(status))
    for path in candidates:
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if f" {wanted} " not in line:
                    continue
                m = _UVICORN_LINE_RE.search(line)
                if not m:
                    continue
                st = m.group("status")
                if st != wanted:
                    continue
                raw_path = m.group("path") or ""
                # Normalize query strings away for grouping.
                raw_path = raw_path.split("?", 1)[0]
                counts[raw_path] += 1
        except Exception:  # noqa: BLE001
            continue
    return dict(counts)


def _report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("NeuroLeague Playtest Report (latest)")
    lines.append("=" * 34)
    lines.append(f"- generated_at: {report.get('generated_at')}")
    lines.append(f"- range_days: {report.get('range_days')}")
    if report.get("demo_replay_id"):
        lines.append(f"- demo_replay_id: {report.get('demo_replay_id')}")
    lines.append("")

    playtest = report.get("playtest_v1") if isinstance(report.get("playtest_v1"), dict) else {}
    steps = playtest.get("steps") if isinstance(playtest.get("steps"), list) else []
    if steps:
        lines.append("Playtest funnel (unique actors)")
        lines.append("-" * 30)
        for row in steps:
            if not isinstance(row, dict):
                continue
            name = str(row.get("step") or "")
            users = int(row.get("users") or 0)
            conv = row.get("conv_from_prev")
            conv_s = f"{(float(conv) * 100):.1f}%" if isinstance(conv, (int, float)) else "—"
            med = row.get("median_time_to_step_sec")
            lines.append(f"- {name}: users={users} · conv={conv_s} · median={_fmt_seconds(float(med) if isinstance(med, (int, float)) else None)}")
        lines.append("")

    remix = report.get("remix_v3_demo") if isinstance(report.get("remix_v3_demo"), dict) else {}
    rsteps = remix.get("steps") if isinstance(remix.get("steps"), list) else []
    if rsteps:
        lines.append("Remix v3 demo funnel (best-effort)")
        lines.append("-" * 30)
        for row in rsteps:
            if not isinstance(row, dict):
                continue
            name = str(row.get("step") or "")
            users = int(row.get("actors") or 0)
            conv = row.get("conv_from_prev")
            conv_s = f"{(float(conv) * 100):.1f}%" if isinstance(conv, (int, float)) else "—"
            lines.append(f"- {name}: actors={users} · conv={conv_s}")
        lines.append("")

    errors = report.get("top_errors") if isinstance(report.get("top_errors"), dict) else {}
    db_rows = errors.get("db") if isinstance(errors.get("db"), list) else []
    if db_rows:
        lines.append("Top HTTP errors (db, curated)")
        lines.append("-" * 30)
        for row in db_rows[:10]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {int(row.get('status') or 0)} {str(row.get('path') or '')}: {int(row.get('count') or 0)}"
            )
        lines.append("")

    log_429 = errors.get("log_429") if isinstance(errors.get("log_429"), list) else []
    if log_429:
        lines.append("429s (best-effort from logs)")
        lines.append("-" * 30)
        for row in log_429[:10]:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {str(row.get('path') or '')}: {int(row.get('count') or 0)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a playtest summary report from the DB.")
    parser.add_argument("--db-url", default=None, help="Override NEUROLEAGUE_DB_URL (sqlite/postgres).")
    parser.add_argument("--days", type=int, default=7, help="Lookback range in days (default: 7).")
    args = parser.parse_args(argv)

    root_dir = Path(__file__).resolve().parents[1]
    demo_replay_id = _load_demo_replay_id(root_dir=root_dir)

    # Late imports so --db-url can override env-backed Settings() defaults where needed.
    if args.db_url:
        import os

        os.environ["NEUROLEAGUE_DB_URL"] = str(args.db_url)

    from neuroleague_api.core.config import Settings
    from neuroleague_api.models import Event, HttpErrorEvent

    settings = Settings()
    engine = create_engine(str(args.db_url or settings.db_url), future=True)
    SessionMaker = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    days = max(1, min(365, int(args.days)))
    now = datetime.now(UTC)
    start_dt = now - timedelta(days=days)

    report: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "range_days": days,
        "start": start_dt.isoformat(),
        "end": now.isoformat(),
        "demo_replay_id": demo_replay_id,
    }

    with SessionMaker() as session:
        _build_playtest_section(session=session, start_dt=start_dt, end_dt=now, out=report)
        _build_remix_v3_section(session=session, start_dt=start_dt, end_dt=now, demo_replay_id=demo_replay_id, out=report)
        _build_errors_section(session=session, start_dt=start_dt, end_dt=now, root_dir=root_dir, out=report)

    # Outputs
    ops_dir = root_dir / "artifacts" / "ops"
    handoff_dir = root_dir / "artifacts" / "handoff"
    ops_dir.mkdir(parents=True, exist_ok=True)
    handoff_dir.mkdir(parents=True, exist_ok=True)

    json_bytes = orjson.dumps(report, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    (ops_dir / "playtest_report_latest.json").write_bytes(json_bytes)
    (handoff_dir / "playtest_report_latest.txt").write_text(_report_text(report), encoding="utf-8")

    # Best-effort: also publish under storage backend (for S3/MinIO deploys).
    try:
        from neuroleague_api.storage_backend import get_storage_backend

        backend = get_storage_backend()
        backend.put_bytes(
            key="ops/playtest_report_latest.json",
            data=json_bytes,
            content_type="application/json",
        )
    except Exception:  # noqa: BLE001
        pass

    print(f"Wrote: {ops_dir / 'playtest_report_latest.json'}")
    print(f"Wrote: {handoff_dir / 'playtest_report_latest.txt'}")
    return 0


def _build_playtest_section(*, session: Session, start_dt: datetime, end_dt: datetime, out: dict[str, Any]) -> None:
    from neuroleague_api.models import Event

    rows = session.scalars(
        select(Event)
        .where(Event.created_at >= start_dt)
        .where(Event.created_at < end_dt)
        .where(Event.type.in_(["playtest_opened", "playtest_step_completed", "playtest_completed"]))
        .order_by(Event.created_at.asc(), Event.id.asc())
    ).all()

    actors: dict[str, _PlaytestActor] = {}
    for ev in rows:
        payload = _safe_payload(ev)
        key = _subject_key(user_id=str(ev.user_id) if ev.user_id else None, payload=payload)
        if not key:
            continue
        actor = actors.get(key)
        if actor is None:
            actor = _PlaytestActor(opened_at=None, completed_at=None, step_at={})
            actors[key] = actor
        ts = _dt_aware(ev.created_at)

        if str(ev.type) == "playtest_opened":
            actor.opened_at = ts if actor.opened_at is None else min(actor.opened_at, ts)
            continue
        if str(ev.type) == "playtest_completed":
            actor.completed_at = (
                ts if actor.completed_at is None else min(actor.completed_at, ts)
            )
            continue

        # playtest_step_completed
        meta = payload.get("meta")
        step_id = None
        if isinstance(meta, dict):
            try:
                step_id = int(meta.get("step_id"))
            except Exception:  # noqa: BLE001
                step_id = None
        if step_id is None or not (1 <= int(step_id) <= 6):
            continue
        st = actor.ensure()
        st[int(step_id)] = ts if int(step_id) not in st else min(st[int(step_id)], ts)

    # Normalize start times (opened_at fallback).
    for actor in actors.values():
        if actor.opened_at is not None:
            continue
        earliest: datetime | None = None
        if actor.step_at:
            for t in actor.step_at.values():
                earliest = t if earliest is None else min(earliest, t)
        if actor.completed_at:
            earliest = (
                actor.completed_at if earliest is None else min(earliest, actor.completed_at)
            )
        actor.opened_at = earliest

    def _count_step(step_id: int) -> int:
        n = 0
        for a in actors.values():
            if a.step_at and step_id in a.step_at:
                n += 1
        return n

    def _median_time_to(step_id: int) -> float | None:
        deltas: list[float] = []
        for a in actors.values():
            if not a.opened_at:
                continue
            if not a.step_at or step_id not in a.step_at:
                continue
            dt = (a.step_at[step_id] - a.opened_at).total_seconds()
            if dt >= 0:
                deltas.append(float(dt))
        return _median(deltas)

    def _median_time_to_completed() -> float | None:
        deltas: list[float] = []
        for a in actors.values():
            if not a.opened_at or not a.completed_at:
                continue
            dt = (a.completed_at - a.opened_at).total_seconds()
            if dt >= 0:
                deltas.append(float(dt))
        return _median(deltas)

    opened = sum(1 for a in actors.values() if a.opened_at is not None)
    steps_out: list[dict[str, Any]] = []

    prev = opened
    steps_out.append(
        {
            "step": "playtest_opened",
            "users": int(opened),
            "conv_from_prev": None,
            "median_time_to_step_sec": 0.0 if opened else None,
        }
    )
    for i in range(1, 7):
        n = _count_step(i)
        steps_out.append(
            {
                "step": f"playtest_step_{i}",
                "users": int(n),
                "conv_from_prev": _pct(n, prev) if prev else 0.0,
                "median_time_to_step_sec": _median_time_to(i),
            }
        )
        prev = n

    completed = sum(1 for a in actors.values() if a.completed_at is not None)
    steps_out.append(
        {
            "step": "playtest_completed",
            "users": int(completed),
            "conv_from_prev": _pct(completed, prev) if prev else 0.0,
            "median_time_to_step_sec": _median_time_to_completed(),
        }
    )

    out["playtest_v1"] = {
        "unique_actors": int(len(actors)),
        "steps": steps_out,
    }


def _build_remix_v3_section(
    *,
    session: Session,
    start_dt: datetime,
    end_dt: datetime,
    demo_replay_id: str | None,
    out: dict[str, Any],
) -> None:
    from neuroleague_api.models import Event

    funnel_steps = [
        "share_open",
        "beat_this_click",
        "challenge_created",
        "match_done",
        "reply_clip_created",
        "reply_clip_shared",
    ]

    rows = session.scalars(
        select(Event)
        .where(Event.created_at >= start_dt)
        .where(Event.created_at < end_dt)
        .where(Event.type.in_(funnel_steps))
        .order_by(Event.created_at.asc(), Event.id.asc())
    ).all()

    def actor_key(ev: Event, payload: dict[str, Any], *, prefer_match_map: bool) -> str | None:
        match_id = str(payload.get("match_id") or "").strip()
        if prefer_match_map and match_id and match_id in match_actor:
            return match_actor[match_id]
        ip_hash = payload.get("ip_hash")
        ua_hash = payload.get("user_agent_hash")
        if isinstance(ip_hash, str) and isinstance(ua_hash, str) and ip_hash and ua_hash:
            return f"a:{ip_hash[:24]}:{ua_hash[:24]}"
        if ev.user_id:
            return f"u:{str(ev.user_id)}"
        dev = payload.get("device_id")
        if isinstance(dev, str) and dev.strip():
            return f"d:{dev.strip()[:80]}"
        return None

    def parent_replay_id(ev_type: str, payload: dict[str, Any]) -> str | None:
        if ev_type == "reply_clip_shared":
            meta = payload.get("meta")
            if isinstance(meta, dict):
                rid = str(meta.get("parent_replay_id") or meta.get("replay_id") or "").strip()
                return rid or None
            return None
        rid = str(payload.get("parent_replay_id") or payload.get("replay_id") or "").strip()
        return rid or None

    match_actor: dict[str, str] = {}
    match_parent: dict[str, str] = {}
    actors_by_step: dict[str, set[str]] = defaultdict(set)

    for ev in rows:
        payload = _safe_payload(ev)
        t = str(ev.type)
        match_id = str(payload.get("match_id") or "").strip()

        # Prefer mapping for steps emitted from async workers (no ip_hash).
        prefer_match_map = t in {"match_done", "reply_clip_created"}
        akey = actor_key(ev, payload, prefer_match_map=prefer_match_map)
        if not akey:
            continue

        # Build match_id -> actor mapping from request-backed events.
        if t == "challenge_created" and match_id:
            match_actor.setdefault(match_id, akey)
            pr = parent_replay_id(t, payload)
            if pr:
                match_parent.setdefault(match_id, pr)

        # Filter to demo replay_id when available.
        if demo_replay_id:
            pr = parent_replay_id(t, payload)
            if t in {"match_done", "reply_clip_created"} and match_id and match_id in match_parent:
                pr = match_parent.get(match_id)
            if t == "share_open":
                if str(payload.get("source") or "") != "s/clip":
                    continue
                if str(payload.get("replay_id") or "").strip() != demo_replay_id:
                    continue
            else:
                if pr != demo_replay_id:
                    continue

        actors_by_step[t].add(akey)

    steps_out: list[dict[str, Any]] = []
    prev = 0
    for i, step in enumerate(funnel_steps):
        n = int(len(actors_by_step.get(step, set())))
        steps_out.append(
            {
                "step": step,
                "actors": n,
                "conv_from_prev": None if i == 0 else _pct(n, prev) if prev else 0.0,
            }
        )
        prev = n

    out["remix_v3_demo"] = {
        "demo_replay_id": demo_replay_id,
        "steps": steps_out,
    }


def _build_errors_section(
    *,
    session: Session,
    start_dt: datetime,
    end_dt: datetime,
    root_dir: Path,
    out: dict[str, Any],
) -> None:
    from neuroleague_api.models import HttpErrorEvent

    rows = session.execute(
        select(HttpErrorEvent.status, HttpErrorEvent.path, func.count(HttpErrorEvent.id))
        .where(HttpErrorEvent.created_at >= start_dt)
        .where(HttpErrorEvent.created_at < end_dt)
        .group_by(HttpErrorEvent.status, HttpErrorEvent.path)
    ).all()

    grouped = [
        {"status": int(status or 0), "path": str(path or ""), "count": int(count or 0)}
        for status, path, count in rows
    ]
    grouped.sort(key=lambda r: (-int(r.get("count") or 0), int(r.get("status") or 0), str(r.get("path") or "")))

    # 429s are intentionally not persisted in HttpErrorEvent; try to infer from local logs.
    log_429_counts = _scan_logs_for_status_counts(root_dir=root_dir, status=429)
    log_429_rows = [
        {"path": p, "count": int(c)} for p, c in sorted(log_429_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    out["top_errors"] = {
        "db": grouped[:20],
        "log_429": log_429_rows[:20],
        "note": "DB excludes 429 by design; log_429 is best-effort from local file logs (if present).",
    }


if __name__ == "__main__":
    raise SystemExit(main())

