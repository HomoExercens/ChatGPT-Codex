from __future__ import annotations

import orjson


def test_cache_key_render_profile_changes_hash() -> None:
    from neuroleague_api.clip_render import cache_key

    base = cache_key(
        replay_digest="d" * 12,
        kind="clip_mp4",
        start_tick=0,
        end_tick=20,
        fps=12,
        scale=1,
        theme="dark",
        aspect="9:16",
        captions_version="capv5",
        captions_template_id="A",
    )
    hq = cache_key(
        replay_digest="d" * 12,
        kind="clip_mp4",
        start_tick=0,
        end_tick=20,
        fps=30,
        scale=2,
        theme="dark",
        aspect="9:16",
        captions_version="capv5",
        captions_template_id="A",
        render_profile="creator_kit_hq:kitv2",
    )
    assert base != hq


def test_creator_kit_hq_queues_render_job(api_client) -> None:
    r = api_client.get("/s/clip/r_test_seed/kit.zip?start=0.0&end=1.0&hq=1")
    assert r.status_code == 202
    payload = r.json()
    assert payload.get("queued") is True
    job_id = str(payload.get("job_id") or "")
    assert job_id.startswith("rj_")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob

    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        assert job is not None
        assert job.kind == "clip"
        assert job.status in ("queued", "running", "done", "failed")
        params = orjson.loads(job.params_json or "{}")
        assert isinstance(params, dict)
        assert params.get("creator_kit_hq") is True
        assert params.get("creator_kit_version") == "kitv2"
        assert int(params.get("scale") or 0) == 2
        assert int(params.get("fps") or 0) == 30
