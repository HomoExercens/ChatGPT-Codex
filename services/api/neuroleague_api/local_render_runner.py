from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
import threading
import time
from typing import Any

import orjson
from sqlalchemy import asc, select

from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal
from neuroleague_api.models import RenderJob
from neuroleague_api.render_runner import (
    run_render_clip_job,
    run_render_sharecard_job,
    run_render_thumbnail_job,
)


@dataclass(frozen=True)
class LocalRenderRunnerConfig:
    poll_interval_sec: float = 0.5
    max_workers: int = 2


class LocalRenderRunner:
    def __init__(self, *, config: LocalRenderRunnerConfig | None = None) -> None:
        self._cfg = config or LocalRenderRunnerConfig()
        self._stop = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=int(self._cfg.max_workers))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001
            pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(float(self._cfg.poll_interval_sec))

    def _tick(self) -> None:
        settings = Settings()
        with SessionLocal() as session:
            job = session.scalar(
                select(RenderJob)
                .where(RenderJob.status == "queued")
                .where(RenderJob.ray_job_id.is_(None))
                .order_by(asc(RenderJob.created_at), asc(RenderJob.id))
                .limit(1)
            )
            if not job:
                return
            job_id = str(job.id)

            with self._lock:
                if job_id in self._inflight:
                    return
                self._inflight.add(job_id)

            # Mark as running quickly so we don't re-pick it.
            try:
                job.status = "running"
                job.progress = max(1, int(job.progress or 0))
                job.error_message = None
                session.add(job)
                session.commit()
            except Exception:  # noqa: BLE001
                with self._lock:
                    self._inflight.discard(job_id)
                return

        def run() -> None:
            try:
                self._run_job(job_id=job_id, settings=settings)
            finally:
                with self._lock:
                    self._inflight.discard(job_id)

        self._executor.submit(run)

    def _run_job(self, *, job_id: str, settings: Settings) -> None:
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if not job:
                return
            kind = str(job.kind or "")
            replay_id = str(job.target_replay_id or "")
            try:
                params = (
                    orjson.loads(job.params_json) if job.params_json else {}
                )  # type: ignore[assignment]
            except Exception:  # noqa: BLE001
                params = {}

        try:
            if kind == "thumbnail":
                run_render_thumbnail_job(
                    job_id=job_id,
                    replay_id=replay_id,
                    start_tick=int(params.get("start_tick") or 0),
                    end_tick=int(params.get("end_tick") or 0),
                    scale=int(params.get("scale") or 1),
                    theme=str(params.get("theme") or "dark"),
                    db_url=settings.db_url,
                    artifacts_dir=settings.artifacts_dir,
                )
                return

            if kind == "clip":
                run_render_clip_job(
                    job_id=job_id,
                    replay_id=replay_id,
                    start_tick=int(params.get("start_tick") or 0),
                    end_tick=int(params.get("end_tick") or 0),
                    format=str(params.get("format") or "webm"),
                    fps=int(params.get("fps") or 12),
                    scale=int(params.get("scale") or 1),
                    theme=str(params.get("theme") or "dark"),
                    aspect=str(params.get("aspect") or "16:9"),
                    captions=bool(params.get("captions") or False),
                    db_url=settings.db_url,
                    artifacts_dir=settings.artifacts_dir,
                )
                return

            if kind == "sharecard":
                run_render_sharecard_job(
                    job_id=job_id,
                    replay_id=replay_id,
                    theme=str(params.get("theme") or "dark"),
                    locale=str(params.get("locale") or "en"),
                    db_url=settings.db_url,
                    artifacts_dir=settings.artifacts_dir,
                )
                return

            raise RuntimeError(f"unsupported_render_job_kind:{kind}")
        except Exception as exc:  # noqa: BLE001
            with SessionLocal() as session:
                job = session.get(RenderJob, job_id)
                if job:
                    job.status = "failed"
                    job.progress = min(100, max(0, int(job.progress or 0)))
                    job.error_message = str(exc)[:800]
                    job.finished_at = job.finished_at or datetime.now(UTC)
                    session.add(job)
                    session.commit()


_RUNNER: LocalRenderRunner | None = None


def start_local_render_runner() -> LocalRenderRunner:
    global _RUNNER
    if _RUNNER is not None:
        return _RUNNER
    runner = LocalRenderRunner()
    runner.start()
    _RUNNER = runner
    return runner


def stop_local_render_runner() -> None:
    global _RUNNER
    if _RUNNER is None:
        return
    _RUNNER.stop()
    _RUNNER = None

