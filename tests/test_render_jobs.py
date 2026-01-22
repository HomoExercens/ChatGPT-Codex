from __future__ import annotations

from datetime import UTC, datetime

import orjson


def test_render_job_thumbnail_lifecycle_and_cache_reuse(api_client) -> None:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob, Replay
    from neuroleague_api.ray_tasks import run_render_thumbnail_job
    from neuroleague_api.clip_render import cache_key

    settings = Settings()
    now = datetime.now(UTC)

    with SessionLocal() as session:
        replay = session.get(Replay, "r_test_seed")
        assert replay is not None
        digest = str(replay.digest or "")
        assert digest

        start_tick = 0
        end_tick = 40
        key = cache_key(
            replay_digest=digest,
            kind="thumbnail",
            start_tick=start_tick,
            end_tick=end_tick,
            fps=1,
            scale=1,
            theme="dark",
        )

        job_id = "rj_test_thumb_1"
        job = RenderJob(
            id=job_id,
            user_id="user_demo",
            kind="thumbnail",
            target_replay_id=replay.id,
            target_match_id=replay.match_id,
            params_json=orjson.dumps(
                {
                    "start_tick": start_tick,
                    "end_tick": end_tick,
                    "scale": 1,
                    "theme": "dark",
                }
            ).decode("utf-8"),
            cache_key=key,
            status="queued",
            progress=0,
            ray_job_id=None,
            artifact_path=None,
            error_message=None,
            created_at=now,
            finished_at=None,
        )
        session.add(job)
        session.commit()

    out_path = run_render_thumbnail_job(
        job_id=job_id,
        replay_id="r_test_seed",
        start_tick=0,
        end_tick=40,
        scale=1,
        theme="dark",
        db_url=settings.db_url,
        artifacts_dir=settings.artifacts_dir,
    )
    assert out_path.endswith(".png")

    job_resp = api_client.get(f"/api/render_jobs/{job_id}", headers=headers)
    assert job_resp.status_code == 200
    data = job_resp.json()
    assert data["status"] == "done"
    assert data["artifact_url"]

    thumb_resp = api_client.get(data["artifact_url"], headers=headers)
    assert thumb_resp.status_code == 200
    assert "image/png" in thumb_resp.headers.get("content-type", "")

    # Cache reuse: thumbnail_jobs returns the existing job when cache_key matches.
    reuse = api_client.post(
        "/api/replays/r_test_seed/thumbnail_jobs",
        headers=headers,
        json={"start": 0.0, "end": 2.0, "scale": 1, "theme": "dark"},
    )
    assert reuse.status_code == 200
    assert reuse.json()["cache_key"] == key
    assert reuse.json()["job_id"] == job_id
