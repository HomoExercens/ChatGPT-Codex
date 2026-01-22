from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import orjson
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import RenderJob

router = APIRouter(prefix="/api/render_jobs", tags=["render_jobs"])


class RenderJobOut(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    progress: int
    cache_key: str
    artifact_url: str | None
    error_message: str | None
    params: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


def _maybe_refresh_ray_status(db: Session, job: RenderJob) -> None:
    if job.status not in ("queued", "running"):
        return
    if not job.ray_job_id:
        return
    try:
        from neuroleague_api.ray_runtime import ensure_ray
        import ray  # type: ignore
    except Exception:  # noqa: BLE001
        return

    ensure_ray()

    raw = job.ray_job_id.strip()
    if raw.startswith("ObjectRef(") and raw.endswith(")"):
        raw = raw[len("ObjectRef(") : -1]
    try:
        obj_ref = ray.ObjectRef.from_hex(raw)
    except Exception:  # noqa: BLE001
        return

    ready, _ = ray.wait([obj_ref], timeout=0)
    if not ready:
        return

    try:
        ray.get(obj_ref)
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error_message = str(exc)[:800]
        job.progress = min(100, max(0, int(job.progress or 0)))
        job.finished_at = job.finished_at or datetime.now(UTC)
        db.add(job)
        db.commit()
    else:
        try:
            db.refresh(job)
        except Exception:  # noqa: BLE001
            pass


def _artifact_url(job: RenderJob) -> str | None:
    if job.status != "done":
        return None
    if not job.target_replay_id:
        return None

    params: dict[str, Any] = {}
    try:
        params = orjson.loads(job.params_json) if job.params_json else {}  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        params = {}

    if job.kind == "thumbnail":
        start_tick = int(params.get("start_tick") or 0)
        end_tick = int(params.get("end_tick") or (start_tick + 1))
        scale = int(params.get("scale") or 1)
        theme = str(params.get("theme") or "dark")
        start = f"{start_tick / 20:.1f}"
        end = f"{end_tick / 20:.1f}"
        return (
            f"/api/replays/{job.target_replay_id}/thumbnail?"
            f"start={start}&end={end}&scale={scale}&theme={theme}&async=0"
        )

    if job.kind == "clip":
        start_tick = int(params.get("start_tick") or 0)
        end_tick = int(params.get("end_tick") or (start_tick + 1))
        fps = int(params.get("fps") or 12)
        scale = int(params.get("scale") or 1)
        theme = str(params.get("theme") or "dark")
        fmt = str(params.get("format") or "webm")
        aspect = str(params.get("aspect") or "16:9")
        captions = bool(params.get("captions") or False)
        start = f"{start_tick / 20:.1f}"
        end = f"{end_tick / 20:.1f}"
        return (
            f"/api/replays/{job.target_replay_id}/clip?"
            f"start={start}&end={end}&format={fmt}&fps={fps}&scale={scale}&theme={theme}"
            f"&aspect={aspect}&captions={1 if captions else 0}&async=0"
        )

    if job.kind == "sharecard":
        theme = str(params.get("theme") or "dark")
        locale = str(params.get("locale") or "en")
        return (
            f"/api/replays/{job.target_replay_id}/sharecard?"
            f"theme={theme}&locale={locale}&async=0"
        )

    return None


@router.get("/{job_id}", response_model=RenderJobOut)
def get_job(
    job_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> RenderJobOut:
    job = db.get(RenderJob, job_id)
    if not job or job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Render job not found")
    _maybe_refresh_ray_status(db, job)
    params: dict[str, Any] = {}
    try:
        params = orjson.loads(job.params_json) if job.params_json else {}
    except Exception:  # noqa: BLE001
        params = {}
    return RenderJobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,  # type: ignore[arg-type]
        progress=int(job.progress or 0),
        cache_key=job.cache_key,
        artifact_url=_artifact_url(job),
        error_message=job.error_message,
        params=params,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )
