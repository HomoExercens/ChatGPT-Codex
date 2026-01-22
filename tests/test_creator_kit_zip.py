from __future__ import annotations

import io
import zipfile


def test_creator_kit_zip_contains_expected_files_and_etag(api_client, seeded_db) -> None:
    from neuroleague_api.clip_render import (
        CAPTIONS_VERSION,
        captions_plan_for_segment,
        cache_key,
        clamp_clip_params,
    )
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Replay
    from neuroleague_api.routers.share import _placeholder_png_bytes
    from neuroleague_api.storage import load_replay_json
    from neuroleague_api.storage_backend import get_storage_backend

    backend = get_storage_backend()

    with SessionLocal() as db:
        replay = db.get(Replay, "r_test_seed")
        assert replay is not None
        payload = load_replay_json(artifact_path=replay.artifact_path)
        digest = str(replay.digest or payload.get("digest") or "")
        assert digest

    s, e = 0.0, 12.0
    start_tick, end_tick, fps, scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=s,
        end_sec=e,
        fps=12,
        scale=1,
        max_duration_sec=12.0,
    )
    plan = captions_plan_for_segment(
        replay_payload=payload, start_tick=start_tick, end_tick=end_tick
    )
    mp4_key = cache_key(
        replay_digest=digest,
        kind="clip_mp4",
        start_tick=start_tick,
        end_tick=end_tick,
        fps=fps,
        scale=scale,
        theme="dark",
        aspect="9:16",
        captions_version=plan.version or CAPTIONS_VERSION,
        captions_template_id=plan.template_id,
    )
    mp4_asset_key = f"clips/mp4/clip_mp4_r_test_seed_{mp4_key[:16]}.mp4"
    mp4_path = backend.local_path(key=mp4_asset_key)
    mp4_path.parent.mkdir(parents=True, exist_ok=True)
    mp4_path.write_bytes(b"dummy-mp4")

    th_start_tick, th_end_tick, _fps_th, th_scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=s,
        end_sec=e,
        fps=10,
        scale=1,
        max_duration_sec=12.0,
    )
    thumb_key = cache_key(
        replay_digest=digest,
        kind="thumbnail",
        start_tick=th_start_tick,
        end_tick=th_end_tick,
        fps=1,
        scale=th_scale,
        theme="dark",
    )
    thumb_asset_key = f"clips/thumbnails/thumb_r_test_seed_{thumb_key[:16]}.png"
    thumb_path = backend.local_path(key=thumb_asset_key)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_path.write_bytes(_placeholder_png_bytes())

    url = "/s/clip/r_test_seed/kit.zip?start=0&end=12&ref=test"
    resp = api_client.get(url)
    assert resp.status_code == 200
    etag = resp.headers.get("etag")
    assert etag
    assert "immutable" in str(resp.headers.get("cache-control") or "").lower()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert names == {
        "neuroleague_best_clip_r_test_seed.mp4",
        "neuroleague_thumb_r_test_seed.png",
        "neuroleague_caption_r_test_seed.txt",
        "neuroleague_qr_r_test_seed.png",
    }

    resp_304 = api_client.get(url, headers={"If-None-Match": etag})
    assert resp_304.status_code == 304

