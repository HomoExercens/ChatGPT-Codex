from __future__ import annotations

from collections import Counter, deque
from threading import Lock
from typing import Iterable

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from neuroleague_api.db import SessionLocal
from neuroleague_api.models import Event, HttpErrorEvent, Match, RenderJob


_HTTP_LOCK = Lock()
_HTTP_REQUESTS: Counter[tuple[str, str, str]] = Counter()
_HTTP_LATENCY_BUCKETS_S: tuple[float, ...] = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
_HTTP_LATENCY_BINS: dict[tuple[str, str], list[int]] = {}
_HTTP_LATENCY_SUM_S: dict[tuple[str, str], float] = {}
_HTTP_LATENCY_COUNT: dict[tuple[str, str], int] = {}

# (epoch_sec, path, method, status, request_id)
_RECENT_ERRORS: deque[tuple[int, str, str, int, str | None]] = deque()
_RECENT_ERRORS_MAX = 50_000

_INTERESTING_4XX: set[int] = {400, 401, 403, 404, 409, 422}


def inc_http_request(*, path: str, method: str, status: str) -> None:
    key = (str(path), str(method), str(status))
    with _HTTP_LOCK:
        _HTTP_REQUESTS[key] += 1


def observe_http_request(
    *,
    path: str,
    method: str,
    status: str,
    duration_ms: float | None = None,
    request_id: str | None = None,
    now_s: int | None = None,
) -> None:
    now = int(now_s or time.time())
    path_s = str(path)
    method_s = str(method)
    status_s = str(status)

    try:
        status_i = int(status_s)
    except Exception:  # noqa: BLE001
        status_i = 0

    dur_s: float | None = None
    if duration_ms is not None:
        try:
            dur_s = max(0.0, float(duration_ms) / 1000.0)
        except Exception:  # noqa: BLE001
            dur_s = None

    key = (path_s, method_s, status_s)
    latency_key = (path_s, method_s)

    with _HTTP_LOCK:
        _HTTP_REQUESTS[key] += 1

        if dur_s is not None:
            bins = _HTTP_LATENCY_BINS.get(latency_key)
            if bins is None:
                bins = [0 for _ in range(len(_HTTP_LATENCY_BUCKETS_S) + 1)]
                _HTTP_LATENCY_BINS[latency_key] = bins

            idx = len(_HTTP_LATENCY_BUCKETS_S)
            for i, edge in enumerate(_HTTP_LATENCY_BUCKETS_S):
                if dur_s <= float(edge):
                    idx = i
                    break
            bins[idx] += 1

            _HTTP_LATENCY_SUM_S[latency_key] = float(
                _HTTP_LATENCY_SUM_S.get(latency_key, 0.0)
            ) + float(dur_s)
            _HTTP_LATENCY_COUNT[latency_key] = int(
                _HTTP_LATENCY_COUNT.get(latency_key, 0)
            ) + 1

        if status_i >= 400:
            _RECENT_ERRORS.append((now, path_s, method_s, status_i, request_id))
            while len(_RECENT_ERRORS) > _RECENT_ERRORS_MAX:
                _RECENT_ERRORS.popleft()


def record_http_error_event(
    *,
    path: str,
    method: str,
    status: int,
    request_id: str | None,
    created_at: datetime | None = None,
) -> None:
    # Persist a small, curated subset so /ops can aggregate across instances.
    try:
        status_i = int(status)
    except Exception:  # noqa: BLE001
        return
    if status_i < 400:
        return
    if status_i == 429:
        return
    if status_i < 500 and status_i not in _INTERESTING_4XX:
        return

    path_s = str(path or "")
    if path_s.startswith("/api/assets/"):
        # allowlist endpoints intentionally return 404s; avoid noisy storage.
        if status_i == 404:
            return

    now = created_at or datetime.now(UTC)
    try:
        with SessionLocal() as session:
            session.add(
                HttpErrorEvent(
                    id=f"he_{uuid4().hex}",
                    created_at=now,
                    path=path_s[:240] or "/",
                    method=str(method or "")[:16] or "GET",
                    status=int(status_i),
                    request_id=(str(request_id)[:80] if request_id else None),
                )
            )
            session.commit()
    except Exception:  # noqa: BLE001
        pass


def recent_http_errors_db(
    db: Session, *, minutes: int = 60, limit: int = 10, now: datetime | None = None
) -> list[dict[str, object]]:
    minutes = max(1, min(24 * 60, int(minutes)))
    limit = max(1, min(50, int(limit)))
    now_dt = now or datetime.now(UTC)
    cutoff = now_dt - timedelta(minutes=int(minutes))

    grouped = db.execute(
        select(
            HttpErrorEvent.path,
            HttpErrorEvent.method,
            HttpErrorEvent.status,
            func.count(HttpErrorEvent.id),
            func.max(HttpErrorEvent.created_at),
        )
        .where(HttpErrorEvent.created_at >= cutoff)
        .group_by(HttpErrorEvent.path, HttpErrorEvent.method, HttpErrorEvent.status)
        .order_by(func.count(HttpErrorEvent.id).desc(), HttpErrorEvent.path.asc())
        .limit(int(limit))
    ).all()

    out: list[dict[str, object]] = []
    for path, method, status, count, last_at in grouped:
        last_row = db.execute(
            select(HttpErrorEvent.request_id, HttpErrorEvent.created_at)
            .where(HttpErrorEvent.created_at >= cutoff)
            .where(HttpErrorEvent.path == path)
            .where(HttpErrorEvent.method == method)
            .where(HttpErrorEvent.status == status)
            .order_by(HttpErrorEvent.created_at.desc(), HttpErrorEvent.id.desc())
            .limit(1)
        ).first()
        last_req = None
        last_ts: datetime | None = None
        if last_row:
            last_req = str(last_row[0] or "").strip() or None
            last_ts = last_row[1] if isinstance(last_row[1], datetime) else None
        out.append(
            {
                "path": str(path or ""),
                "method": str(method or ""),
                "status": int(status or 0),
                "count": int(count or 0),
                "last_request_id": last_req,
                "last_at_s": int(last_ts.timestamp()) if last_ts else None,
            }
        )
    return out


def cleanup_http_error_events(
    db: Session, *, keep_days: int = 3, now: datetime | None = None
) -> int:
    keep_days = max(1, min(30, int(keep_days)))
    now_dt = now or datetime.now(UTC)
    cutoff = now_dt - timedelta(days=keep_days)
    try:
        deleted = db.query(HttpErrorEvent).filter(HttpErrorEvent.created_at < cutoff).delete()  # type: ignore[attr-defined]
        db.commit()
        return int(deleted or 0)
    except Exception:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


def _snapshot_http() -> list[tuple[tuple[str, str, str], int]]:
    with _HTTP_LOCK:
        return list(_HTTP_REQUESTS.items())


def _snapshot_latency() -> list[tuple[tuple[str, str], list[int], float, int]]:
    with _HTTP_LOCK:
        out: list[tuple[tuple[str, str], list[int], float, int]] = []
        for key, bins in _HTTP_LATENCY_BINS.items():
            out.append(
                (
                    key,
                    list(bins),
                    float(_HTTP_LATENCY_SUM_S.get(key, 0.0)),
                    int(_HTTP_LATENCY_COUNT.get(key, 0)),
                )
            )
        return out


def recent_http_errors(
    *, minutes: int = 60, limit: int = 10, now_s: int | None = None
) -> list[dict[str, object]]:
    minutes = max(1, min(24 * 60, int(minutes)))
    limit = max(1, min(50, int(limit)))
    now = int(now_s or time.time())
    cutoff = now - (minutes * 60)

    with _HTTP_LOCK:
        rows = [row for row in _RECENT_ERRORS if row[0] >= cutoff]

    counts: Counter[tuple[str, str, int]] = Counter()
    last: dict[tuple[str, str, int], tuple[int, str | None]] = {}
    for ts, path, method, status, request_id in rows:
        k = (str(path), str(method), int(status))
        counts[k] += 1
        prev = last.get(k)
        if prev is None or ts >= prev[0]:
            last[k] = (int(ts), request_id)

    items = sorted(counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:limit]
    out: list[dict[str, object]] = []
    for (path, method, status), count in items:
        ts, req_id = last.get((path, method, status), (0, None))
        out.append(
            {
                "path": path,
                "method": method,
                "status": int(status),
                "count": int(count),
                "last_request_id": req_id,
                "last_at_s": int(ts) if ts else None,
            }
        )
    return out


def _fmt_labels(**labels: str) -> str:
    def esc(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    parts = [f'{k}="{esc(v)}"' for k, v in labels.items()]
    return "{" + ",".join(parts) + "}" if parts else ""


def _render_counter(
    *,
    name: str,
    help_text: str,
    rows: Iterable[tuple[dict[str, str], int]],
) -> str:
    lines: list[str] = [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} counter",
    ]
    for labels, value in rows:
        lines.append(f"{name}{_fmt_labels(**labels)} {int(value)}")
    return "\n".join(lines) + "\n"


def _render_histogram(
    *,
    name: str,
    help_text: str,
    buckets: Iterable[float],
    rows: Iterable[tuple[dict[str, str], list[int], float, int]],
) -> str:
    lines: list[str] = [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} histogram",
    ]
    bucket_edges = [float(b) for b in buckets]
    for labels, bin_counts, sum_s, count in rows:
        base_labels = dict(labels)
        cumulative = 0
        for i, edge in enumerate(bucket_edges):
            cumulative += int(bin_counts[i]) if i < len(bin_counts) else 0
            lines.append(
                f"{name}_bucket{_fmt_labels(**base_labels, le=str(edge))} {cumulative}"
            )
        cumulative += int(bin_counts[len(bucket_edges)]) if len(bin_counts) > len(
            bucket_edges
        ) else 0
        lines.append(
            f"{name}_bucket{_fmt_labels(**base_labels, le='+Inf')} {cumulative}"
        )
        lines.append(f"{name}_sum{_fmt_labels(**base_labels)} {float(sum_s):.6f}")
        lines.append(f"{name}_count{_fmt_labels(**base_labels)} {int(count)}")
    return "\n".join(lines) + "\n"


def render_prometheus_metrics(*, db: Session) -> str:
    out: list[str] = []

    http_rows = [
        ({"path": path, "method": method, "status": status}, count)
        for (path, method, status), count in sorted(_snapshot_http())
    ]
    out.append(
        _render_counter(
            name="neuroleague_http_requests_total",
            help_text="Total HTTP requests processed by this API process.",
            rows=http_rows,
        )
    )

    latency_rows = [
        ({"path": path, "method": method}, bins, sum_s, count)
        for ((path, method), bins, sum_s, count) in sorted(_snapshot_latency())
    ]
    out.append(
        _render_histogram(
            name="neuroleague_http_request_duration_seconds",
            help_text="HTTP request duration (seconds) by route template and method (in-process).",
            buckets=_HTTP_LATENCY_BUCKETS_S,
            rows=latency_rows,
        )
    )

    match_rows = db.execute(
        select(Match.mode, Match.result, func.count(Match.id))
        .where(Match.status == "done")
        .group_by(Match.mode, Match.result)
    ).all()
    out.append(
        _render_counter(
            name="neuroleague_matches_total",
            help_text="Total completed matches by mode and result (raw Match.result).",
            rows=[
                ({"mode": str(mode), "result": str(result)}, int(cnt or 0))
                for (mode, result, cnt) in match_rows
            ],
        )
    )

    rj_rows = db.execute(
        select(RenderJob.kind, RenderJob.status, func.count(RenderJob.id)).group_by(
            RenderJob.kind, RenderJob.status
        )
    ).all()
    out.append(
        _render_counter(
            name="neuroleague_render_jobs_total",
            help_text="Total render jobs by kind and status.",
            rows=[
                ({"kind": str(kind), "status": str(status)}, int(cnt or 0))
                for (kind, status, cnt) in rj_rows
            ],
        )
    )

    clip_types = (
        "clip_view",
        "clip_like",
        "clip_share",
        "clip_fork_click",
        "clip_open_ranked",
        "clip_completion",
    )
    ev_rows = db.execute(
        select(Event.type, func.count(Event.id))
        .where(Event.type.in_(clip_types))
        .group_by(Event.type)
    ).all()
    out.append(
        _render_counter(
            name="neuroleague_clips_events_total",
            help_text="Clip-related events by type.",
            rows=[({"type": str(t)}, int(cnt or 0)) for (t, cnt) in ev_rows],
        )
    )

    return "\n".join(out)
