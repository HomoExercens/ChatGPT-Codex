from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.models import Event, RenderJob
from neuroleague_api.storage import resolve_local_artifact_path
from neuroleague_api.storage_backend import get_storage_backend


_PURGE_KINDS = {"thumbnail", "clip", "clip_mp4", "sharecard"}


def cleanup_render_jobs(
    session: Session,
    *,
    now: datetime | None = None,
    done_ttl: timedelta = timedelta(days=7),
    orphan_ttl: timedelta = timedelta(hours=12),
    purge_artifacts: bool = False,
    keep_shared_ttl: timedelta | None = None,
    dry_run: bool = False,
    delete_limit: int = 2000,
) -> dict[str, int]:
    now_dt = now or datetime.now(UTC)
    cutoff_done = now_dt - done_ttl
    cutoff_orphan = now_dt - orphan_ttl
    cutoff_shared = now_dt - keep_shared_ttl if keep_shared_ttl else None

    keep_replay_ids: set[str] = set()
    keep_match_ids: set[str] = set()
    if purge_artifacts and cutoff_shared is not None:
        rows = session.scalars(
            select(Event.payload_json)
            .where(Event.type == "share_open")
            .where(Event.created_at >= cutoff_shared)
            .order_by(Event.created_at.desc())
            .limit(10_000)
        ).all()
        for raw in rows:
            try:
                obj = orjson.loads((raw or "{}").encode("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(obj, dict):
                continue
            rid = obj.get("replay_id")
            mid = obj.get("match_id")
            if isinstance(rid, str) and rid:
                keep_replay_ids.add(rid)
            if isinstance(mid, str) and mid:
                keep_match_ids.add(mid)

    orphaned = session.scalars(
        select(RenderJob)
        .where(RenderJob.status.in_(("queued", "running")))
        .where(RenderJob.created_at < cutoff_orphan)
        .order_by(RenderJob.created_at.asc(), RenderJob.id.asc())
        .limit(int(delete_limit))
    ).all()

    orphan_marked = 0
    if not dry_run:
        for job in orphaned:
            job.status = "failed"
            job.error_message = (
                (job.error_message or "").strip() or "orphaned by ops-clean"
            )[:800]
            job.finished_at = now_dt
            session.add(job)
            orphan_marked += 1
    else:
        orphan_marked = len(orphaned)

    prune_candidates = session.scalars(
        select(RenderJob)
        .where(RenderJob.status.in_(("done", "failed")))
        .where(
            or_(
                and_(
                    RenderJob.finished_at.is_not(None),
                    RenderJob.finished_at < cutoff_done,
                ),
                and_(
                    RenderJob.finished_at.is_(None), RenderJob.created_at < cutoff_done
                ),
            )
        )
        .order_by(RenderJob.created_at.asc(), RenderJob.id.asc())
        .limit(int(delete_limit))
    ).all()

    artifacts_deleted = 0
    jobs_deleted = 0
    skipped_recently_shared = 0

    artifacts_root = Path(Settings().artifacts_dir).resolve()
    backend = get_storage_backend()

    for job in prune_candidates:
        if (
            purge_artifacts
            and keep_shared_ttl is not None
            and (
                job.target_replay_id in keep_replay_ids
                or job.target_match_id in keep_match_ids
            )
        ):
            skipped_recently_shared += 1
            continue

        if (
            purge_artifacts
            and job.artifact_path
            and str(job.kind or "") in _PURGE_KINDS
        ):
            try:
                counted = False
                p = resolve_local_artifact_path(job.artifact_path)
                if p is not None:
                    resolved = p.resolve()
                    if (
                        resolved != artifacts_root
                        and artifacts_root not in resolved.parents
                    ):
                        raise ValueError("artifact path escapes artifacts root")
                    if resolved.is_file():
                        if not dry_run:
                            resolved.unlink(missing_ok=True)  # type: ignore[arg-type]
                        artifacts_deleted += 1
                        counted = True

                if not counted:
                    # Try deleting as a storage key (works for S3 backend, too).
                    raw_key = (
                        str(job.artifact_path or "")
                        .strip()
                        .replace("\\", "/")
                        .lstrip("/")
                    )
                    if raw_key.startswith(("clips/", "sharecards/", "ops/")):
                        if not dry_run:
                            if backend.delete(key=raw_key):
                                artifacts_deleted += 1
                        else:
                            artifacts_deleted += 1
            except Exception:  # noqa: BLE001
                pass

        if not dry_run:
            session.delete(job)
        jobs_deleted += 1

    if not dry_run:
        session.commit()
    else:
        session.rollback()

    return {
        "orphan_marked_failed": orphan_marked,
        "jobs_deleted": jobs_deleted,
        "artifacts_deleted": artifacts_deleted,
        "skipped_recently_shared": skipped_recently_shared,
    }
