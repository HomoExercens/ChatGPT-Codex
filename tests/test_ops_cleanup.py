from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson


def test_ops_cleanup_deletes_old_jobs_and_optional_artifacts(seeded_db) -> None:
    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob
    from neuroleague_api.ops_cleanup import cleanup_render_jobs

    settings = Settings()
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    job_id = "rj_test_cleanup_done"
    cache_key = "ck_test_cleanup_done"
    key = "clips/thumbnails/test_cleanup.png"
    p = Path(settings.artifacts_dir) / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"png")

    with SessionLocal() as session:
        session.add(
            RenderJob(
                id=job_id,
                user_id="user_demo",
                kind="thumbnail",
                target_replay_id="r_test_seed",
                target_match_id="m_test_seed",
                params_json=orjson.dumps({"start_tick": 0, "end_tick": 40}).decode(
                    "utf-8"
                ),
                cache_key=cache_key,
                status="done",
                progress=100,
                ray_job_id=None,
                artifact_path=key,
                error_message=None,
                created_at=old,
                finished_at=old,
            )
        )
        session.commit()

        out = cleanup_render_jobs(
            session,
            now=now,
            done_ttl=timedelta(days=7),
            orphan_ttl=timedelta(hours=12),
            purge_artifacts=True,
            delete_limit=100,
        )
        assert out["jobs_deleted"] >= 1
        assert out["artifacts_deleted"] >= 1

    assert not p.exists()
    with SessionLocal() as session:
        assert session.get(RenderJob, job_id) is None


def test_ops_cleanup_marks_orphan_jobs_failed(seeded_db) -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob
    from neuroleague_api.ops_cleanup import cleanup_render_jobs

    now = datetime.now(UTC)
    old = now - timedelta(hours=36)
    job_id = "rj_test_cleanup_orphan"

    with SessionLocal() as session:
        session.add(
            RenderJob(
                id=job_id,
                user_id="user_demo",
                kind="clip",
                target_replay_id="r_test_seed",
                target_match_id="m_test_seed",
                params_json="{}",
                cache_key="ck_test_cleanup_orphan",
                status="running",
                progress=10,
                ray_job_id=None,
                artifact_path=None,
                error_message=None,
                created_at=old,
                finished_at=None,
            )
        )
        session.commit()

        out = cleanup_render_jobs(
            session,
            now=now,
            done_ttl=timedelta(days=7),
            orphan_ttl=timedelta(hours=12),
            purge_artifacts=False,
            delete_limit=100,
        )
        assert out["orphan_marked_failed"] >= 1

    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert "orphaned" in (job.error_message or "")
        session.delete(job)
        session.commit()
