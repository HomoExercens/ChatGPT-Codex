from __future__ import annotations


def test_share_clip_landing_has_og_meta(api_client) -> None:
    resp = api_client.get("/s/clip/r_test_seed?start=0.0&end=2.0")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    html = resp.text

    for key in (
        'property="og:title"',
        'property="og:description"',
        'property="og:image"',
        'property="og:image:alt"',
        'property="og:url"',
        'name="twitter:card"',
    ):
        assert key in html

    # Ensure absolute URLs are used.
    assert "http://testserver/s/clip/r_test_seed" in html
    assert "http://testserver/s/clip/r_test_seed/thumb.png" in html
    assert "/s/qr.png?next=" in html
    assert "Copy Caption" in html
    assert "Copy App Link" in html


def test_share_clip_thumbnail_endpoint_never_404(api_client) -> None:
    resp = api_client.get("/s/clip/r_test_seed/thumb.png?start=0.0&end=1.0")
    assert resp.status_code == 200
    assert "image/png" in resp.headers.get("content-type", "")


def test_share_build_landing_exposes_build_code_copy(api_client) -> None:
    resp = api_client.get("/s/build/bp_demo_1v1")
    assert resp.status_code == 200
    html = resp.text
    assert "Build Code" in html
    assert "Copy Build Code" in html
    assert 'id="build_code"' in html
    assert "NL1_" in html


def test_share_qr_endpoint_is_cacheable_and_never_404(api_client) -> None:
    resp = api_client.get("/s/qr.png?next=%2Fhome&src=test_qr")
    assert resp.status_code == 200
    assert "image/png" in resp.headers.get("content-type", "")
    assert resp.headers.get("etag")
    etag = resp.headers["etag"]

    resp2 = api_client.get("/s/qr.png?next=%2Fhome&src=test_qr", headers={"if-none-match": etag})
    assert resp2.status_code == 304


def test_share_clip_video_mp4_is_cacheable_and_supports_range(api_client) -> None:
    from neuroleague_api.clip_render import CAPTIONS_VERSION, captions_plan_for_segment, cache_key, clamp_clip_params
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Replay
    from neuroleague_api.storage import load_replay_json
    from neuroleague_api.storage_backend import get_storage_backend

    with SessionLocal() as db:
        replay = db.get(Replay, "r_test_seed")
        assert replay is not None
        payload = load_replay_json(artifact_path=replay.artifact_path)
        digest = str(replay.digest or payload.get("digest") or "")
        assert digest

    start_tick, end_tick, fps, scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=0.0,
        end_sec=2.0,
        fps=12,
        scale=1,
        max_duration_sec=12.0,
    )
    captions_plan = captions_plan_for_segment(
        replay_payload=payload, start_tick=start_tick, end_tick=end_tick
    )
    key = cache_key(
        replay_digest=digest,
        kind="clip_mp4",
        start_tick=start_tick,
        end_tick=end_tick,
        fps=fps,
        scale=scale,
        theme="dark",
        aspect="9:16",
        captions_version=captions_plan.version or CAPTIONS_VERSION,
        captions_template_id=captions_plan.template_id,
    )

    backend = get_storage_backend()
    asset_key = f"clips/mp4/clip_mp4_r_test_seed_{key[:16]}.mp4"
    local = backend.local_path(key=asset_key)
    assert local is not None
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(b"0123456789abcdef" * 256)

    url = "/s/clip/r_test_seed/video.mp4?start=0.0&end=2.0&aspect=9:16"

    head = api_client.head(url)
    assert head.status_code == 200
    assert "video/mp4" in head.headers.get("content-type", "")
    assert "immutable" in (head.headers.get("cache-control") or "")
    assert head.headers.get("etag")

    resp = api_client.get(url)
    assert resp.status_code == 200
    assert "video/mp4" in resp.headers.get("content-type", "")
    assert "immutable" in (resp.headers.get("cache-control") or "")
    etag = resp.headers.get("etag")
    assert etag == f"\"mp4_{key[:32]}\""

    resp2 = api_client.get(url, headers={"if-none-match": etag})
    assert resp2.status_code == 304

    resp3 = api_client.get(url, headers={"range": "bytes=0-3"})
    assert resp3.status_code == 206
    assert resp3.headers.get("content-range", "").startswith("bytes 0-3/")
    assert len(resp3.content) == 4
