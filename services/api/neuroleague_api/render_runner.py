from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import orjson


def run_render_thumbnail_job(
    *,
    job_id: str,
    replay_id: str,
    start_tick: int,
    end_tick: int,
    scale: int,
    theme: str,
    db_url: str,
    artifacts_dir: str,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob, Replay
    from neuroleague_api.storage import (
        load_replay_json,
        resolve_local_artifact_path,
    )
    from neuroleague_api.storage_backend import get_storage_backend
    from neuroleague_api.clip_render import render_thumbnail_png_bytes

    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        if not job:
            return "missing"
        cache_key = str(job.cache_key or "")
        if job.status == "done" and job.artifact_path:
            p = resolve_local_artifact_path(job.artifact_path)
            if p is not None and p.exists():
                return job.artifact_path
            try:
                if get_storage_backend().exists(key=job.artifact_path):
                    return job.artifact_path
            except Exception:  # noqa: BLE001
                pass
        job.status = "running"
        job.progress = 5
        job.error_message = None
        session.add(job)
        session.commit()

    try:
        with SessionLocal() as session:
            replay = session.get(Replay, replay_id)
            if not replay:
                raise RuntimeError("Replay not found")
            payload = load_replay_json(artifact_path=replay.artifact_path)

        safe_prefix = (cache_key[:16] if cache_key else job_id[-12:]) or "unknown"
        asset_key = f"clips/thumbnails/thumb_{replay_id}_{safe_prefix}.png"
        backend = get_storage_backend()

        if not backend.exists(key=asset_key):
            png = render_thumbnail_png_bytes(
                replay_payload=payload,
                start_tick=int(start_tick),
                end_tick=int(end_tick),
                scale=int(scale),
                theme=str(theme),
            )
            backend.put_bytes(key=asset_key, data=png, content_type="image/png")

        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.artifact_path = asset_key
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        return asset_key
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "failed"
                job.progress = min(100, max(0, int(job.progress or 0)))
                job.error_message = str(exc)[:800]
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        raise


def run_render_clip_job(
    *,
    job_id: str,
    replay_id: str,
    start_tick: int,
    end_tick: int,
    format: str,
    fps: int,
    scale: int,
    theme: str,
    aspect: str = "16:9",
    captions: bool = False,
    db_url: str,
    artifacts_dir: str,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob, Replay
    from neuroleague_api.storage import (
        load_replay_json,
        resolve_local_artifact_path,
    )
    from neuroleague_api.storage_backend import get_storage_backend
    from neuroleague_api.clip_render import (
        caption_lines_for_segment,
        render_gif_bytes,
        render_mp4_to_path,
        render_webm_to_path,
    )

    captions_template_id: str | None = None
    mp4_preset: str | None = None
    mp4_crf: int | None = None
    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        if not job:
            return "missing"
        try:
            params = (
                orjson.loads(job.params_json) if job.params_json else {}
            )  # type: ignore[assignment]
        except Exception:  # noqa: BLE001
            params = {}
        if isinstance(params, dict):
            raw_tpl = params.get("captions_template_id")
            captions_template_id = str(raw_tpl) if raw_tpl else None
            raw_preset = params.get("mp4_preset")
            mp4_preset = str(raw_preset).strip()[:24] if raw_preset else None
            try:
                raw_crf = params.get("mp4_crf")
                mp4_crf = int(raw_crf) if raw_crf is not None else None
            except Exception:  # noqa: BLE001
                mp4_crf = None

        cache_key = str(job.cache_key or "")
        if job.status == "done" and job.artifact_path:
            p = resolve_local_artifact_path(job.artifact_path)
            if p is not None and p.exists():
                return job.artifact_path
            try:
                if get_storage_backend().exists(key=job.artifact_path):
                    return job.artifact_path
            except Exception:  # noqa: BLE001
                pass
        job.status = "running"
        job.progress = 5
        job.error_message = None
        session.add(job)
        session.commit()

    try:
        with SessionLocal() as session:
            replay = session.get(Replay, replay_id)
            if not replay:
                raise RuntimeError("Replay not found")
            payload = load_replay_json(artifact_path=replay.artifact_path)

        fmt = str(format).lower()
        if fmt not in ("gif", "webm", "mp4"):
            fmt = "webm"
        safe_prefix = (cache_key[:16] if cache_key else job_id[-12:]) or "unknown"
        asset_key = f"clips/{fmt}/clip_{fmt}_{replay_id}_{safe_prefix}.{fmt}"
        backend = get_storage_backend()
        out_path = backend.local_path(key=asset_key)

        if not backend.exists(key=asset_key):
            captions_lines = (
                caption_lines_for_segment(
                    replay_payload=payload,
                    start_tick=int(start_tick),
                    end_tick=int(end_tick),
                    template_id=captions_template_id,
                )
                if captions
                else None
            )
            if fmt == "gif":
                gif = render_gif_bytes(
                    replay_payload=payload,
                    start_tick=int(start_tick),
                    end_tick=int(end_tick),
                    fps=int(fps),
                    scale=int(scale),
                    theme=str(theme),
                    aspect=aspect,  # type: ignore[arg-type]
                    captions_lines=captions_lines,
                    captions_template_id=captions_template_id,
                )
                backend.put_bytes(key=asset_key, data=gif, content_type="image/gif")
            elif fmt == "mp4":
                if out_path is not None:
                    render_mp4_to_path(
                        replay_payload=payload,
                        start_tick=int(start_tick),
                        end_tick=int(end_tick),
                        fps=int(fps),
                        scale=int(scale),
                        theme=str(theme),
                        out_path=out_path,
                        aspect=aspect,  # type: ignore[arg-type]
                        captions_lines=captions_lines,
                        mp4_preset=mp4_preset or "ultrafast",
                        mp4_crf=int(mp4_crf) if mp4_crf is not None else 28,
                        captions_template_id=captions_template_id,
                    )
                else:
                    from tempfile import TemporaryDirectory

                    with TemporaryDirectory(prefix="neuroleague_mp4_") as tmpdir:
                        tmp_path = Path(tmpdir) / f"clip_{replay_id}_{safe_prefix}.mp4"
                        render_mp4_to_path(
                            replay_payload=payload,
                            start_tick=int(start_tick),
                            end_tick=int(end_tick),
                            fps=int(fps),
                            scale=int(scale),
                            theme=str(theme),
                            out_path=tmp_path,
                            aspect=aspect,  # type: ignore[arg-type]
                            captions_lines=captions_lines,
                            mp4_preset=mp4_preset or "ultrafast",
                            mp4_crf=int(mp4_crf) if mp4_crf is not None else 28,
                            captions_template_id=captions_template_id,
                        )
                        backend.put_file(
                            key=asset_key, path=tmp_path, content_type="video/mp4"
                        )
            else:
                if out_path is not None:
                    render_webm_to_path(
                        replay_payload=payload,
                        start_tick=int(start_tick),
                        end_tick=int(end_tick),
                        fps=int(fps),
                        scale=int(scale),
                        theme=str(theme),
                        out_path=out_path,
                        aspect=aspect,  # type: ignore[arg-type]
                        captions_lines=captions_lines,
                        captions_template_id=captions_template_id,
                    )
                else:
                    from tempfile import TemporaryDirectory

                    with TemporaryDirectory(prefix="neuroleague_webm_") as tmpdir:
                        tmp_path = Path(tmpdir) / f"clip_{replay_id}_{safe_prefix}.webm"
                        render_webm_to_path(
                            replay_payload=payload,
                            start_tick=int(start_tick),
                            end_tick=int(end_tick),
                            fps=int(fps),
                            scale=int(scale),
                            theme=str(theme),
                            out_path=tmp_path,
                            aspect=aspect,  # type: ignore[arg-type]
                            captions_lines=captions_lines,
                            captions_template_id=captions_template_id,
                        )
                        backend.put_file(
                            key=asset_key, path=tmp_path, content_type="video/webm"
                        )

        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.artifact_path = asset_key
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        return asset_key
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "failed"
                job.progress = min(100, max(0, int(job.progress or 0)))
                job.error_message = str(exc)[:800]
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        raise


def run_render_sharecard_job(
    *,
    job_id: str,
    replay_id: str,
    theme: str,
    locale: str,
    db_url: str,
    artifacts_dir: str,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Match, RenderJob, Replay
    from neuroleague_api.storage import (
        load_replay_json,
        resolve_local_artifact_path,
    )
    from neuroleague_api.storage_backend import get_storage_backend
    from neuroleague_api.routers.replays import (
        _render_sharecard_png_v1,
        _render_sharecard_png_v2,
        _sharecard_html_v2,
    )

    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        if not job:
            return "missing"
        if job.status == "done" and job.artifact_path:
            p = resolve_local_artifact_path(job.artifact_path)
            if p is not None and p.exists():
                return job.artifact_path
            try:
                if get_storage_backend().exists(key=job.artifact_path):
                    return job.artifact_path
            except Exception:  # noqa: BLE001
                pass
        job.status = "running"
        job.progress = 5
        job.error_message = None
        session.add(job)
        session.commit()

    try:
        with SessionLocal() as session:
            replay = session.get(Replay, replay_id)
            if not replay:
                raise RuntimeError("Replay not found")
            match = session.get(Match, replay.match_id)
            if not match:
                raise RuntimeError("Match not found")
            payload = load_replay_json(artifact_path=replay.artifact_path)
            digest = str(replay.digest or payload.get("digest") or "")
            safe_digest = digest[:12] if digest else "unknown"

        key_v2 = f"sharecards/sharecard_v2_{replay_id}_{safe_digest}_{theme}_{locale}.png"
        key_v1 = f"sharecards/sharecard_v1_{replay_id}_{safe_digest}.png"
        backend = get_storage_backend()

        force_v1 = os.environ.get("NEUROLEAGUE_E2E_FAST") == "1"
        if force_v1:
            if not backend.exists(key=key_v1):
                backend.put_bytes(
                    key=key_v1,
                    data=_render_sharecard_png_v1(replay_payload=payload, match=match),
                    content_type="image/png",
                )
            chosen_key = key_v1
        else:
            if not backend.exists(key=key_v2):
                html = _sharecard_html_v2(
                    replay_payload=payload, match=match, theme=theme, locale=locale
                )
                try:
                    local = backend.local_path(key=key_v2)
                    if local is not None:
                        _render_sharecard_png_v2(html=html, out_path=local)
                    else:
                        from tempfile import TemporaryDirectory

                        with TemporaryDirectory(prefix="neuroleague_sharecard_") as tmpdir:
                            tmp_path = Path(tmpdir) / f"sharecard_v2_{replay_id}_{safe_digest}.png"
                            _render_sharecard_png_v2(html=html, out_path=tmp_path)
                            backend.put_file(
                                key=key_v2, path=tmp_path, content_type="image/png"
                            )
                except Exception:  # noqa: BLE001
                    if not backend.exists(key=key_v1):
                        backend.put_bytes(
                            key=key_v1,
                            data=_render_sharecard_png_v1(
                                replay_payload=payload, match=match
                            ),
                            content_type="image/png",
                        )
                    chosen_key = key_v1
                else:
                    chosen_key = key_v2
            else:
                chosen_key = key_v2

        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.artifact_path = chosen_key
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        return chosen_key
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "failed"
                job.progress = min(100, max(0, int(job.progress or 0)))
                job.error_message = str(exc)[:800]
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        raise
