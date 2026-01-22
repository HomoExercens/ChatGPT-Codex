from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import html
import shutil
from io import BytesIO
from typing import Any, Literal
from urllib.parse import quote
import zipfile
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from neuroleague_api.build_code import encode_build_code
from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal
from neuroleague_api.eventlog import (
    ip_hash_from_request,
    log_event,
    user_agent_hash_from_request,
)
from neuroleague_api.experiments import assign_experiment
from neuroleague_api.models import Blueprint, Challenge, Match, Rating, Replay, User
from neuroleague_api.share_caption import (
    SHARE_CAPTION_VERSION,
    build_share_caption,
    challenge_share_caption,
    clip_share_caption,
    profile_share_caption,
)
from neuroleague_api.storage import ensure_artifacts_dir, load_replay_json
from neuroleague_api.storage_backend import get_storage_backend

from neuroleague_sim.models import BlueprintSpec
from sqlalchemy import desc, select


router = APIRouter(prefix="/s", tags=["share"])

_PLACEHOLDER_PNG: bytes | None = None


def _platform_guess(request: Request) -> str:
    ua = str(request.headers.get("user-agent") or "").lower()
    if "twitter" in ua:
        return "twitter"
    if "discord" in ua:
        return "discord"
    if "slack" in ua:
        return "slack"
    if "facebook" in ua or "meta" in ua:
        return "facebook"
    if "kakaotalk" in ua:
        return "kakao"
    if "line/" in ua:
        return "line"
    return "unknown"


def _placeholder_png_bytes() -> bytes:
    global _PLACEHOLDER_PNG
    if _PLACEHOLDER_PNG is not None:
        return _PLACEHOLDER_PNG

    from PIL import Image, ImageDraw

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), (15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (40, 40, w - 40, h - 40), radius=40, outline=(51, 65, 85), width=3
    )
    draw.text((72, 86), "NEUROLEAGUE", fill=(226, 232, 240))
    draw.text((72, 128), "Clip Preview", fill=(148, 163, 184))
    draw.text((72, 170), "Open in app to watch the replay.", fill=(148, 163, 184))

    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    _PLACEHOLDER_PNG = buf.getvalue()
    return _PLACEHOLDER_PNG


def _abs_base(request: Request) -> str:
    settings = Settings()
    if settings.public_base_url:
        return str(settings.public_base_url).rstrip("/")
    return str(request.base_url).rstrip("/")


def _clamp_seconds(
    *, start: float, end: float | None, max_duration_sec: float = 12.0
) -> tuple[float, float | None]:
    s = float(start or 0.0)
    e = float(end) if end is not None else None
    if s < 0:
        s = 0.0
    if e is not None and e < 0:
        e = 0.0
    if e is not None and e < s:
        s, e = e, s
    # Keep share clips short for safety.
    if e is not None and (e - s) > float(max_duration_sec):
        e = s + float(max_duration_sec)
    return s, e


def _clip_len_variant(raw: str | None) -> str | None:
    v = str(raw or "").strip()
    if v in {"10s", "12s", "15s"}:
        return v
    return None


def _max_duration_for_clip_len_variant(variant: str | None) -> float:
    if variant == "10s":
        return 10.0
    if variant == "15s":
        return 15.0
    return 12.0


def _safe_captions_version(raw: str | None) -> str | None:
    v = str(raw or "").strip()
    return v[:32] if v else None


def _safe_captions_template_id(raw: str | None) -> str | None:
    v = str(raw or "").strip()
    return v[:64] if v else None


def _start_href(
    *,
    next_path: str,
    ref: str | None,
    src: str | None = None,
    lenv: str | None = None,
    cv: str | None = None,
    ctpl: str | None = None,
) -> str:
    # Keep this as a relative link so it works when /s/* is served via the web origin
    # (dev proxy, nginx) even if the API sees a different upstream base URL.
    href = f"/start?next={quote(next_path, safe='')}"
    if ref:
        href += f"&ref={quote(str(ref), safe='')}"
    if src:
        href += f"&src={quote(str(src), safe='')}"
    if lenv:
        href += f"&lenv={quote(str(lenv), safe='')}"
    if cv:
        href += f"&cv={quote(str(cv), safe='')}"
    if ctpl:
        href += f"&ctpl={quote(str(ctpl), safe='')}"
    return href


def _sanitize_next_path(raw: str) -> str:
    next_path = str(raw or "").strip()
    if not next_path:
        raise HTTPException(status_code=400, detail="next required")
    if not next_path.startswith("/"):
        raise HTTPException(status_code=400, detail="next must be a relative path")
    if next_path.startswith("//"):
        raise HTTPException(status_code=400, detail="invalid next")
    if next_path.startswith("/\\") or next_path.startswith("/%5c"):
        raise HTTPException(status_code=400, detail="invalid next")
    if "://" in next_path:
        raise HTTPException(status_code=400, detail="invalid next")
    return next_path


_QR_CACHE: dict[str, bytes] = {}

CREATOR_KIT_VERSION = "kitv2"
_CREATOR_KIT_ZIP_DT = (2020, 1, 1, 0, 0, 0)


def _qr_etag_raw(*, target: str, scale: int) -> str:
    return hashlib.sha256(
        f"qr:v1:{target}:scale={int(scale)}".encode("utf-8")
    ).hexdigest()


def _qr_png_bytes_for_target(*, target: str, scale: int) -> tuple[bytes, str]:
    etag_raw = _qr_etag_raw(target=target, scale=int(scale))
    cached = _QR_CACHE.get(etag_raw)
    if cached is None:
        import qrcode

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=int(scale),
            border=2,
        )
        qr.add_data(target)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        cached = buf.getvalue()
        if len(_QR_CACHE) > 256:
            _QR_CACHE.clear()
        _QR_CACHE[etag_raw] = cached
    return cached, etag_raw


@router.get("/qr.png")
def qr_png(
    request: Request,
    next: str = Query(min_length=1, max_length=2048),
    ref: str | None = Query(default=None, max_length=80),
    src: str | None = Query(default=None, max_length=64),
    scale: int = Query(default=6, ge=2, le=10),
) -> Response:
    next_path = _sanitize_next_path(next)
    href = _start_href(next_path=next_path, ref=ref, src=src)
    target = f"{_abs_base(request)}{href}"

    etag_raw = _qr_etag_raw(target=target, scale=int(scale))
    etag = f"\"{etag_raw}\""
    if str(request.headers.get("if-none-match") or "") == etag:
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    cached, _etag_raw = _qr_png_bytes_for_target(target=target, scale=int(scale))
    return Response(
        content=cached,
        media_type="image/png",
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


class ShareTrackRequest(BaseModel):
    type: Literal[
        "caption_copied",
        "link_copied",
        "bestclip_downloaded",
        "clip_completion",
        "clip_share",
    ]
    source: str = Field(min_length=1, max_length=64)
    ref: str | None = Field(default=None, max_length=80)
    meta: dict[str, Any] = Field(default_factory=dict)


class ShareTrackResponse(BaseModel):
    ok: bool = True


@router.post("/track", response_model=ShareTrackResponse)
def track_share_event(req: ShareTrackRequest, request: Request) -> ShareTrackResponse:
    with SessionLocal() as db:
        try:
            log_event(
                db,
                type=req.type,
                user_id=None,
                request=request,
                payload={
                    "source": req.source,
                    "ref": req.ref,
                    "meta": req.meta,
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            db.commit()
        except Exception:  # noqa: BLE001
            pass
    return ShareTrackResponse(ok=True)


@router.get("/clip/{replay_id}/thumb.png")
def clip_thumb(
    replay_id: str,
    request: Request,
    start: float = 0.0,
    end: float | None = None,
    lenv: str | None = None,
    scale: int = 1,
    theme: Literal["dark", "light"] = "dark",
) -> Response:
    # Public thumbnail endpoint for sharing/OG. It never 404s on missing cache.
    clip_len_variant = _clip_len_variant(lenv)
    max_duration_sec = _max_duration_for_clip_len_variant(clip_len_variant)
    s, e = _clamp_seconds(start=start, end=end, max_duration_sec=max_duration_sec)
    ensure_artifacts_dir()
    backend = get_storage_backend()

    # If a real thumbnail is cached via /api/replays/{id}/thumbnail (RenderJob or sync), serve it.
    with SessionLocal() as db:
        replay = db.get(Replay, replay_id)
        if replay:
            payload = load_replay_json(artifact_path=replay.artifact_path)
            digest = str(replay.digest or payload.get("digest") or "")
            if digest:
                from neuroleague_api.clip_render import cache_key, clamp_clip_params

                start_tick, end_tick, _fps, scale = clamp_clip_params(
                    replay_payload=payload,
                    start_sec=s,
                    end_sec=e,
                    fps=10,
                    scale=scale,
                    max_duration_sec=max_duration_sec,
                )
                key = cache_key(
                    replay_digest=digest,
                    kind="thumbnail",
                    start_tick=start_tick,
                    end_tick=end_tick,
                    fps=1,
                    scale=scale,
                    theme=theme,
                    clip_len_variant=clip_len_variant,
                )
                asset_key = f"clips/thumbnails/thumb_{replay_id}_{key[:16]}.png"
                try:
                    local = backend.local_path(key=asset_key)
                except Exception:  # noqa: BLE001
                    local = None
                if local is not None and local.exists():
                    return FileResponse(
                        path=str(local), media_type="image/png", filename=local.name
                    )
                try:
                    if backend.exists(key=asset_key):
                        return RedirectResponse(
                            url=backend.public_url(key=asset_key), status_code=307
                        )
                except Exception:  # noqa: BLE001
                    pass

    return Response(content=_placeholder_png_bytes(), media_type="image/png")


@router.get("/clip/{replay_id}/video.mp4")
def clip_video_mp4(
    replay_id: str,
    request: Request,
    start: float = 0.0,
    end: float | None = None,
    lenv: str | None = None,
    cv: str | None = None,
    ctpl: str | None = None,
    fps: int = 12,
    scale: int = 1,
    theme: Literal["dark", "light"] = "dark",
    aspect: Literal["16:9", "9:16"] = "9:16",
    captions: bool = True,
) -> Response:
    # Public MP4 endpoint for sharing. It serves only cached assets; it does not render on-demand.
    clip_len_variant = _clip_len_variant(lenv)
    max_duration_sec = _max_duration_for_clip_len_variant(clip_len_variant)
    s, e = _clamp_seconds(start=start, end=end, max_duration_sec=max_duration_sec)
    ensure_artifacts_dir()
    backend = get_storage_backend()

    with SessionLocal() as db:
        replay = db.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")
        payload = load_replay_json(artifact_path=replay.artifact_path)
        digest = str(replay.digest or payload.get("digest") or "")
        if not digest:
            raise HTTPException(status_code=500, detail="Replay digest missing")

        from neuroleague_api.clip_render import (
            CAPTIONS_VERSION,
            captions_plan_for_segment,
            cache_key,
            clamp_clip_params,
        )

        start_tick, end_tick, fps, scale = clamp_clip_params(
            replay_payload=payload,
            start_sec=s,
            end_sec=e,
            fps=fps,
            scale=scale,
            max_duration_sec=max_duration_sec,
        )
        captions_plan = (
            captions_plan_for_segment(
                replay_payload=payload, start_tick=start_tick, end_tick=end_tick
            )
            if captions
            else None
        )
        forced_captions_version = _safe_captions_version(cv)
        forced_template_id = _safe_captions_template_id(ctpl)
        captions_version = (
            forced_captions_version
            or (captions_plan.version or CAPTIONS_VERSION)
            if captions_plan
            else None
        )
        captions_template_id = (
            forced_template_id
            or (captions_plan.template_id if captions_plan else None)
        )
        key = cache_key(
            replay_digest=digest,
            kind="clip_mp4",
            start_tick=start_tick,
            end_tick=end_tick,
            fps=fps,
            scale=scale,
            theme=theme,
            aspect=aspect,
            clip_len_variant=clip_len_variant,
            captions_version=captions_version,
            captions_template_id=captions_template_id,
        )
        asset_key = f"clips/mp4/clip_mp4_{replay_id}_{key[:16]}.mp4"
        etag = f"\"mp4_{key[:32]}\""
        if str(request.headers.get("if-none-match") or "").strip() == etag:
            return Response(
                status_code=304,
                headers={
                    "ETag": etag,
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        try:
            local = backend.local_path(key=asset_key)
        except Exception:  # noqa: BLE001
            local = None
        if local is not None and local.exists():
            return FileResponse(
                path=str(local),
                media_type="video/mp4",
                filename=local.name,
                headers={
                    "ETag": etag,
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )
        try:
            if backend.exists(key=asset_key):
                return RedirectResponse(
                    url=backend.public_url(key=asset_key),
                    status_code=307,
                    headers={
                        "ETag": etag,
                        "Cache-Control": "public, max-age=31536000, immutable",
                    },
                )
        except Exception:  # noqa: BLE001
            pass

    raise HTTPException(status_code=404, detail="MP4 not cached yet")


@router.get("/clip/{replay_id}/kit.zip")
def clip_creator_kit_zip(
    replay_id: str,
    request: Request,
    start: float = 0.0,
    end: float | None = None,
    lenv: str | None = None,
    cv: str | None = None,
    ctpl: str | None = None,
    ref: str | None = None,
    hq: int = 0,
) -> Response:
    clip_len_variant = _clip_len_variant(lenv)
    max_duration_sec = _max_duration_for_clip_len_variant(clip_len_variant)
    s, e = _clamp_seconds(start=start, end=end, max_duration_sec=max_duration_sec)
    ensure_artifacts_dir()
    backend = get_storage_backend()

    with SessionLocal() as db:
        replay = db.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")
        match = db.get(Match, replay.match_id) if replay.match_id else None
        match_id = str(match.id) if match else str(replay.match_id or replay_id)

        payload = load_replay_json(artifact_path=replay.artifact_path)
        digest = str(replay.digest or payload.get("digest") or "")
        if not digest:
            raise HTTPException(status_code=500, detail="Replay digest missing")

        from neuroleague_api.clip_render import (
            CAPTIONS_VERSION,
            captions_plan_for_segment,
            cache_key,
            clamp_clip_params,
        )

        hq_mode = bool(int(hq or 0) == 1)
        mp4_req_fps = 30 if hq_mode else 12
        mp4_req_scale = 2 if hq_mode else 1
        mp4_preset = "veryfast" if hq_mode else None
        mp4_crf = 23 if hq_mode else None

        mp4_start_tick, mp4_end_tick, fps, scale = clamp_clip_params(
            replay_payload=payload,
            start_sec=s,
            end_sec=e,
            fps=mp4_req_fps,
            scale=mp4_req_scale,
            max_duration_sec=max_duration_sec,
        )
        captions_plan = captions_plan_for_segment(
            replay_payload=payload, start_tick=mp4_start_tick, end_tick=mp4_end_tick
        )
        forced_captions_version = _safe_captions_version(cv)
        forced_template_id = _safe_captions_template_id(ctpl)
        captions_version = (
            forced_captions_version or (captions_plan.version or CAPTIONS_VERSION)
        )
        captions_template_id = forced_template_id or captions_plan.template_id
        render_profile = f"creator_kit_hq:{CREATOR_KIT_VERSION}" if hq_mode else None
        mp4_key = cache_key(
            replay_digest=digest,
            kind="clip_mp4",
            start_tick=mp4_start_tick,
            end_tick=mp4_end_tick,
            fps=fps,
            scale=scale,
            theme="dark",
            aspect="9:16",
            clip_len_variant=clip_len_variant,
            captions_version=captions_version,
            captions_template_id=captions_template_id,
            render_profile=render_profile,
        )
        mp4_asset_key = f"clips/mp4/clip_mp4_{replay_id}_{mp4_key[:16]}.mp4"

        try:
            mp4_local = backend.local_path(key=mp4_asset_key)
        except Exception:  # noqa: BLE001
            mp4_local = None
        mp4_exists = bool(mp4_local is not None and mp4_local.exists())
        if not mp4_exists:
            try:
                mp4_exists = bool(backend.exists(key=mp4_asset_key))
            except Exception:  # noqa: BLE001
                mp4_exists = False
        if not mp4_exists:
            if not hq_mode:
                raise HTTPException(status_code=404, detail="MP4 not cached yet")

            from neuroleague_api.models import RenderJob

            existing = db.scalar(
                select(RenderJob)
                .where(RenderJob.cache_key == mp4_key)
                .order_by(desc(RenderJob.created_at))
                .limit(1)
            )
            if existing and existing.status in ("queued", "running", "done"):
                return Response(
                    content=orjson.dumps(
                        {
                            "queued": True,
                            "status": existing.status,
                            "job_id": existing.id,
                        }
                    ),
                    status_code=202,
                    media_type="application/json",
                    headers={"Cache-Control": "no-store"},
                )

            now = datetime.now(UTC)
            job = RenderJob(
                id=f"rj_{uuid4().hex}",
                user_id=None,
                kind="clip",
                target_replay_id=replay_id,
                target_match_id=replay.match_id,
                params_json=orjson.dumps(
                    {
                        "start_tick": int(mp4_start_tick),
                        "end_tick": int(mp4_end_tick),
                        "format": "mp4",
                        "fps": int(fps),
                        "scale": int(scale),
                        "theme": "dark",
                        "aspect": "9:16",
                        "captions": True,
                        "captions_version": captions_version,
                        "captions_template_id": captions_template_id,
                        "captions_event_type": captions_plan.event_type,
                        "mp4_preset": mp4_preset,
                        "mp4_crf": mp4_crf,
                        "render_profile": render_profile,
                        "creator_kit_version": CREATOR_KIT_VERSION,
                        "creator_kit_hq": True,
                    }
                ).decode("utf-8"),
                cache_key=mp4_key,
                status="queued",
                progress=0,
                ray_job_id=None,
                artifact_path=None,
                error_message=None,
                created_at=now,
                finished_at=None,
            )
            db.add(job)
            db.commit()

            # Best-effort dispatch: only when Ray is explicitly configured.
            settings = Settings()
            if settings.ray_address:
                try:
                    from neuroleague_api.ray_runtime import ensure_ray
                    from neuroleague_api.ray_tasks import render_clip_job

                    ensure_ray()
                    obj_ref = render_clip_job.remote(
                        job_id=job.id,
                        replay_id=replay_id,
                        start_tick=int(mp4_start_tick),
                        end_tick=int(mp4_end_tick),
                        format="mp4",
                        fps=int(fps),
                        scale=int(scale),
                        theme="dark",
                        aspect="9:16",
                        captions=True,
                        db_url=settings.db_url,
                        artifacts_dir=settings.artifacts_dir,
                    )
                    job.ray_job_id = obj_ref.hex()
                    db.add(job)
                    db.commit()
                except Exception:  # noqa: BLE001
                    pass

            return Response(
                content=orjson.dumps({"queued": True, "status": "queued", "job_id": job.id}),
                status_code=202,
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )

        th_start_tick, th_end_tick, _fps_th, th_scale = clamp_clip_params(
            replay_payload=payload,
            start_sec=s,
            end_sec=e,
            fps=10,
            scale=1,
            max_duration_sec=max_duration_sec,
        )
        thumb_key = cache_key(
            replay_digest=digest,
            kind="thumbnail",
            start_tick=th_start_tick,
            end_tick=th_end_tick,
            fps=1,
            scale=th_scale,
            theme="dark",
            clip_len_variant=clip_len_variant,
        )
        thumb_asset_key = f"clips/thumbnails/thumb_{replay_id}_{thumb_key[:16]}.png"
        try:
            thumb_local = backend.local_path(key=thumb_asset_key)
        except Exception:  # noqa: BLE001
            thumb_local = None
        thumb_exists = bool(thumb_local is not None and thumb_local.exists())
        if not thumb_exists:
            try:
                thumb_exists = bool(backend.exists(key=thumb_asset_key))
            except Exception:  # noqa: BLE001
                thumb_exists = False

        challenge_id: str | None = None
        try:
            ch = db.scalar(
                select(Challenge)
                .where(Challenge.status == "active")
                .where(Challenge.target_replay_id == replay_id)
                .order_by(desc(Challenge.created_at), desc(Challenge.id))
                .limit(1)
            )
            if ch:
                challenge_id = str(ch.id)
        except Exception:  # noqa: BLE001
            challenge_id = None

        blueprint_id = (
            str(getattr(match, "blueprint_a_id", "") or "") if match else None
        ) or None
        cta_line: Literal["Beat This", "Remix This", "Play Now"] = (
            "Beat This"
            if challenge_id
            else "Remix This"
            if blueprint_id
            else "Play Now"
        )

        winner = getattr(match, "result", None) if match else None
        header = payload.get("header") if isinstance(payload, dict) else {}
        if not isinstance(header, dict):
            header = {}
        portal_id = str(header.get("portal_id") or "") or None
        aug_ids: list[str] = []
        aug_raw = header.get("augments_a") or []
        if isinstance(aug_raw, list):
            for a in aug_raw:
                if isinstance(a, dict):
                    aid = str(a.get("augment_id") or "").strip()
                    if aid and aid not in aug_ids:
                        aug_ids.append(aid)

        caption_text = clip_share_caption(
            payload,
            match_result=winner if winner in {"A", "B", "draw"} else None,
            portal_id=portal_id,
            augments=aug_ids,
            start_tick=mp4_start_tick,
            end_tick=mp4_end_tick,
            perspective="A",
            cta=cta_line,
        )

        app_q = f"t={s:.1f}"
        if e is not None:
            app_q += f"&end={e:.1f}"
        next_path = f"/replay/{match_id}?{app_q}"
        href = _start_href(next_path=next_path, ref=ref, src="s/clip_qr")
        target = f"{_abs_base(request)}{href}"
        qr_bytes, qr_etag_raw = _qr_png_bytes_for_target(target=target, scale=6)

        caption_hash = hashlib.sha256(caption_text.encode("utf-8")).hexdigest()
        kit_mode = "hq" if hq_mode else "std"
        kit_seed = (
            f"{CREATOR_KIT_VERSION}:{kit_mode}:{mp4_key}:{thumb_key}:{SHARE_CAPTION_VERSION}:"
            f"{caption_hash}:{qr_etag_raw}"
        )
        kit_key = hashlib.sha256(kit_seed.encode("utf-8")).hexdigest()
        etag = f"\"kit_{kit_key[:32]}\""
        cache_headers = {
            "ETag": etag,
            "Cache-Control": "public, max-age=31536000, immutable",
        }
        if str(request.headers.get("if-none-match") or "").strip() == etag:
            return Response(status_code=304, headers=cache_headers)

        kit_asset_key = f"clips/kits/creator_kit_{replay_id}_{kit_key[:16]}.zip"
        try:
            kit_local = backend.local_path(key=kit_asset_key)
        except Exception:  # noqa: BLE001
            kit_local = None
        if kit_local is not None and kit_local.exists():
            return FileResponse(
                path=str(kit_local),
                media_type="application/zip",
                filename=f"neuroleague_creator_kit_{replay_id}.zip",
                headers=cache_headers,
            )
        try:
            if backend.exists(key=kit_asset_key):
                return RedirectResponse(
                    url=backend.public_url(key=kit_asset_key),
                    status_code=307,
                    headers=cache_headers,
                )
        except Exception:  # noqa: BLE001
            pass

        thumb_bytes: bytes
        if thumb_exists:
            if thumb_local is not None and thumb_local.exists():
                thumb_bytes = thumb_local.read_bytes()
            else:
                thumb_bytes = backend.get_bytes(key=thumb_asset_key)
        else:
            thumb_bytes = _placeholder_png_bytes()

        caption_bytes = (caption_text.rstrip("\n") + "\n").encode("utf-8")

        mp4_name = f"neuroleague_best_clip_{replay_id}.mp4"
        thumb_name = f"neuroleague_thumb_{replay_id}.png"
        caption_name = f"neuroleague_caption_{replay_id}.txt"
        qr_name = f"neuroleague_qr_{replay_id}.png"

        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_STORED) as zf:

            def _zipinfo(name: str) -> zipfile.ZipInfo:
                info = zipfile.ZipInfo(str(name))
                info.date_time = _CREATOR_KIT_ZIP_DT
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (0o644 & 0xFFFF) << 16
                return info

            if mp4_local is not None and mp4_local.exists():
                info = _zipinfo(mp4_name)
                with zf.open(info, mode="w") as dst, mp4_local.open("rb") as src:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
            else:
                mp4_bytes = backend.get_bytes(key=mp4_asset_key)
                zf.writestr(_zipinfo(mp4_name), mp4_bytes)

            zf.writestr(_zipinfo(thumb_name), thumb_bytes)
            zf.writestr(_zipinfo(caption_name), caption_bytes)
            zf.writestr(_zipinfo(qr_name), qr_bytes)

        kit_bytes = zip_buf.getvalue()
        backend.put_bytes(
            key=kit_asset_key, data=kit_bytes, content_type="application/zip"
        )

        try:
            kit_local2 = backend.local_path(key=kit_asset_key)
        except Exception:  # noqa: BLE001
            kit_local2 = None
        if kit_local2 is not None and kit_local2.exists():
            return FileResponse(
                path=str(kit_local2),
                media_type="application/zip",
                filename=f"neuroleague_creator_kit_{replay_id}.zip",
                headers=cache_headers,
            )
        return Response(
            content=kit_bytes, media_type="application/zip", headers=cache_headers
        )


@router.head("/clip/{replay_id}/video.mp4", include_in_schema=False)
def clip_video_mp4_head(
    replay_id: str,
    request: Request,
    start: float = 0.0,
    end: float | None = None,
    lenv: str | None = None,
    cv: str | None = None,
    ctpl: str | None = None,
    fps: int = 12,
    scale: int = 1,
    theme: Literal["dark", "light"] = "dark",
    aspect: Literal["16:9", "9:16"] = "9:16",
    captions: bool = True,
) -> Response:
    return clip_video_mp4(
        replay_id=replay_id,
        request=request,
        start=start,
        end=end,
        lenv=lenv,
        cv=cv,
        ctpl=ctpl,
        fps=fps,
        scale=scale,
        theme=theme,
        aspect=aspect,
        captions=captions,
    )


@router.get("/clip/{replay_id}", response_class=HTMLResponse)
def clip_landing(
    replay_id: str,
    request: Request,
    start: float = 0.0,
    end: float | None = None,
    lenv: str | None = None,
    cv: str | None = None,
    ctpl: str | None = None,
    v: int = 0,
    ref: str | None = None,
) -> HTMLResponse:
    base = _abs_base(request)
    has_range = ("start" in request.query_params) or ("end" in request.query_params)
    challenge_id: str | None = None
    blueprint_id: str | None = None
    cta_order_variant: str = "beat_then_remix"

    with SessionLocal() as db:  # independent session; share pages are public
        replay = db.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")
        match = db.get(Match, replay.match_id)
        match_id = str(match.id) if match else str(replay.match_id or replay_id)
        blueprint_id = (
            str(getattr(match, "blueprint_a_id", "") or "") if match else None
        ) or None

        mode = getattr(match, "mode", None) if match else None
        ruleset = (
            getattr(match, "ruleset_version", None)
            if match
            else Settings().ruleset_version
        )
        winner = getattr(match, "result", None) if match else None
        created_at = getattr(match, "created_at", None) if match else None

        payload = load_replay_json(artifact_path=replay.artifact_path)
        digest = str(replay.digest or payload.get("digest") or "")
        top = (
            (payload.get("highlights") or [{}])[0]
            if isinstance(payload.get("highlights"), list)
            else {}
        )
        top_title = str(top.get("title") or "Turning Point")
        top_summary = str(top.get("summary") or "")

        clip_len_variant = _clip_len_variant(lenv)
        max_duration_sec = _max_duration_for_clip_len_variant(clip_len_variant)
        forced_captions_version = _safe_captions_version(cv)
        forced_template_id = _safe_captions_template_id(ctpl)

        if has_range:
            s, e = _clamp_seconds(start=start, end=end, max_duration_sec=max_duration_sec)
        else:
            try:
                from neuroleague_api.clip_render import best_clip_segment

                st, et = best_clip_segment(payload, max_duration_sec=max_duration_sec)
                s, e = float(st) / 20.0, float(et) / 20.0
            except Exception:  # noqa: BLE001
                s, e = _clamp_seconds(start=start, end=end, max_duration_sec=max_duration_sec)

        try:
            ch = db.scalar(
                select(Challenge)
                .where(Challenge.status == "active")
                .where(Challenge.target_replay_id == replay_id)
                .order_by(desc(Challenge.created_at), desc(Challenge.id))
                .limit(1)
            )
            if ch:
                challenge_id = str(ch.id)
        except Exception:  # noqa: BLE001
            challenge_id = None

        try:
            anon_seed = (
                f"{ip_hash_from_request(request) or ''}|"
                f"{user_agent_hash_from_request(request) or ''}"
            )
            anon_id = hashlib.sha256(anon_seed.encode("utf-8")).hexdigest()
            order_variant, _cfg, _is_new = assign_experiment(
                db,
                subject_type="anon",
                subject_id=anon_id,
                experiment_key="share_landing_clip_order",
            )
            cta_order_variant = str(order_variant or "beat_then_remix")
        except Exception:  # noqa: BLE001
            cta_order_variant = "beat_then_remix"

        try:
            log_event(
                db,
                type="share_open",
                user_id=None,
                request=request,
                payload={
                    "source": "s/clip",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "replay_id": replay_id,
                    "match_id": replay.match_id,
                    "start": round(float(s), 2),
                    "end": round(float(e), 2) if e is not None else None,
                    "vertical": 1 if int(v or 0) == 1 else 0,
                    "variants": {
                        "clip_len_v1": clip_len_variant,
                        "captions_v2": forced_template_id,
                    },
                    "captions_version": forced_captions_version,
                    "captions_template_id": forced_template_id,
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            log_event(
                db,
                type="qr_shown",
                user_id=None,
                request=request,
                payload={
                    "source": "s/clip",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "replay_id": replay_id,
                    "match_id": replay.match_id,
                    "variants": {
                        "clip_len_v1": clip_len_variant,
                        "captions_v2": forced_template_id,
                    },
                    "captions_version": forced_captions_version,
                    "captions_template_id": forced_template_id,
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            db.commit()
        except Exception:  # noqa: BLE001
            pass

    q = f"start={s:.1f}"
    if e is not None:
        q += f"&end={e:.1f}"

    if int(v or 0) == 1:
        q += "&v=1"
    if clip_len_variant:
        q += f"&lenv={quote(str(clip_len_variant), safe='')}"
    if forced_captions_version:
        q += f"&cv={quote(str(forced_captions_version), safe='')}"
    if forced_template_id:
        q += f"&ctpl={quote(str(forced_template_id), safe='')}"
    if ref:
        q += f"&ref={quote(str(ref), safe='')}"

    og_url = f"{base}/s/clip/{replay_id}?{q}"
    og_image = f"{base}/s/clip/{replay_id}/thumb.png?{q}&scale=1&theme=dark"
    og_image_w, og_image_h = 900, 506

    backend = get_storage_backend()

    def abs_url(u: str) -> str:
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return f"{base}{u}"

    vertical_mp4: str | None = None
    if digest:
        try:
            from neuroleague_api.clip_render import (
                CAPTIONS_VERSION,
                captions_plan_for_segment,
                cache_key,
                clamp_clip_params,
            )

            start_tick, end_tick, fps, scale = clamp_clip_params(
                replay_payload=payload,
                start_sec=s,
                end_sec=e,
                fps=12,
                scale=1,
                max_duration_sec=max_duration_sec,
            )
            captions_plan = captions_plan_for_segment(
                replay_payload=payload, start_tick=start_tick, end_tick=end_tick
            )
            captions_version = (
                forced_captions_version
                or (captions_plan.version or CAPTIONS_VERSION)
            )
            captions_template_id = forced_template_id or captions_plan.template_id
            key = cache_key(
                replay_digest=digest,
                kind="clip_mp4",
                start_tick=start_tick,
                end_tick=end_tick,
                fps=fps,
                scale=scale,
                theme="dark",
                aspect="9:16",
                clip_len_variant=clip_len_variant,
                captions_version=captions_version,
                captions_template_id=captions_template_id,
            )
            asset_key = f"clips/mp4/clip_mp4_{replay_id}_{key[:16]}.mp4"
            if backend.exists(key=asset_key):
                vertical_mp4 = abs_url(backend.public_url(key=asset_key))
        except Exception:  # noqa: BLE001
            vertical_mp4 = None

    app_q = f"t={s:.1f}"
    if e is not None:
        app_q += f"&end={e:.1f}"
    next_path = f"/replay/{match_id}?{app_q}"
    app_url = _start_href(
        next_path=next_path,
        ref=ref,
        src="s/clip_open",
        lenv=clip_len_variant,
        cv=forced_captions_version,
        ctpl=forced_template_id,
    )
    settings = Settings()
    install_url = str(settings.android_install_url or "").strip()
    install_cta_html = (
        f'<a class="cta secondary" href="{html.escape(install_url)}">Install App</a>'
        if install_url
        else ""
    )

    remix_url: str | None = None
    if blueprint_id:
        remix_url = _start_href(
            next_path=f"/forge?bp={quote(blueprint_id, safe='')}",
            ref=ref,
            src="s/clip_remix",
            lenv=clip_len_variant,
            cv=forced_captions_version,
            ctpl=forced_template_id,
        )

    ranked_url = _start_href(
        next_path="/ranked",
        ref=ref,
        src="s/clip_ranked",
        lenv=clip_len_variant,
        cv=forced_captions_version,
        ctpl=forced_template_id,
    )

    beat_url = app_url
    if challenge_id:
        beat_url = _start_href(
            next_path=f"/challenge/{quote(challenge_id, safe='')}",
            ref=ref,
            src="s/clip_beat",
            lenv=clip_len_variant,
            cv=forced_captions_version,
            ctpl=forced_template_id,
        )

    title = f"NeuroLeague Clip — {match_id}"
    if top_title:
        title = f"NeuroLeague Clip — {top_title}"
    desc_parts = []
    if mode:
        desc_parts.append(str(mode))
    if winner in {"A", "B", "draw"}:
        desc_parts.append(f"result={winner}")
    if ruleset:
        desc_parts.append(str(ruleset))
    if top_summary:
        desc_parts.append(top_summary)
    description = (
        " · ".join([p for p in desc_parts if p])[:240]
        or "Watch a short replay clip from NeuroLeague."
    )

    # Basic, crawler-friendly HTML (no JS required).
    body_title = html.escape(title)
    body_summary = html.escape(top_summary) if top_summary else ""
    body_meta = (
        f"{html.escape(str(mode or ''))} · {html.escape(str(ruleset or ''))}".strip(
            " ·"
        )
    )
    body_date = (
        created_at.isoformat()
        if isinstance(created_at, datetime)
        else datetime.now(UTC).isoformat()
    )
    discord_msg = f"30s Lab Clip: {top_title} — {og_url}"

    try:
        from neuroleague_api.clip_render import clamp_clip_params

        start_tick, end_tick, _fps, _scale = clamp_clip_params(
            replay_payload=payload,
            start_sec=float(s),
            end_sec=float(e) if e is not None else None,
            fps=12,
            scale=1,
            max_duration_sec=max_duration_sec,
        )
    except Exception:  # noqa: BLE001
        start_tick = int(float(s) * 20.0)
        end_tick = int(float((e if e is not None else (float(s) + 6.0))) * 20.0)

    header = payload.get("header") if isinstance(payload, dict) else {}
    if not isinstance(header, dict):
        header = {}
    portal_id = str(header.get("portal_id") or "") or None
    aug_ids: list[str] = []
    aug_raw = header.get("augments_a") or []
    if isinstance(aug_raw, list):
        for a in aug_raw:
            if isinstance(a, dict):
                aid = str(a.get("augment_id") or "").strip()
                if aid and aid not in aug_ids:
                    aug_ids.append(aid)
    cta_line = "Beat This" if challenge_id else "Remix This" if remix_url else "Play Now"
    caption_text = clip_share_caption(
        payload,
        match_result=winner if winner in {"A", "B", "draw"} else None,
        portal_id=portal_id,
        augments=aug_ids,
        start_tick=start_tick,
        end_tick=end_tick,
        perspective="A",
        cta=cta_line,  # type: ignore[arg-type]
    )

    qr_url = _start_href(
        next_path=next_path,
        ref=ref,
        src="s/clip_qr",
        lenv=clip_len_variant,
        cv=forced_captions_version,
        ctpl=forced_template_id,
    )
    app_link = abs_url(qr_url)
    qr_img = f"{base}/s/qr.png?next={quote(next_path, safe='')}&src=s/clip_qr&scale=6"
    if ref:
        qr_img += f"&ref={quote(str(ref), safe='')}"

    beat_cta = f'<a class="cta secondary" href="{html.escape(beat_url)}">Beat This</a>'
    remix_cta = (
        f'<a class="cta secondary" href="{html.escape(remix_url)}">Remix This</a>'
        if remix_url
        else ""
    )
    secondary_ctas_html = (
        f"{remix_cta}{beat_cta}"
        if remix_url and cta_order_variant == "remix_then_beat"
        else f"{beat_cta}{remix_cta}"
    )

    download_kit_html = ""
    download_mp4_html = ""
    if vertical_mp4:
        kit_url = f"/s/clip/{replay_id}/kit.zip?{q}"
        download_kit_html = (
            f'<a class="cta secondary" href="{html.escape(kit_url)}" download '
            'onclick="track(\'bestclip_downloaded\', {kind: \'kit\', creator_kit_version: '
            f'\'{CREATOR_KIT_VERSION}\'}})">Download Kit</a>'
        )
        download_mp4_html = (
            f'<a class="cta secondary" href="{html.escape(vertical_mp4)}" download '
            'onclick="track(\'bestclip_downloaded\', {kind: \'mp4\'})">Download MP4</a>'
        )

    html_out = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <meta property="og:title" content="{html.escape(title)}" />
    <meta property="og:description" content="{html.escape(description)}" />
    <meta property="og:image" content="{html.escape(og_image)}" />
    <meta property="og:image:secure_url" content="{html.escape(og_image)}" />
    <meta property="og:image:width" content="{og_image_w}" />
    <meta property="og:image:height" content="{og_image_h}" />
    <meta property="og:image:alt" content="NeuroLeague clip thumbnail" />
    <meta property="og:url" content="{html.escape(og_url)}" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{html.escape(title)}" />
    <meta name="twitter:description" content="{html.escape(description)}" />
    <meta name="twitter:image" content="{html.escape(og_image)}" />
    <meta name="twitter:image:alt" content="NeuroLeague clip thumbnail" />
    <style>
      :root {{
        --bg: #0f172a;
        --panel: rgba(2,6,23,.55);
        --border: rgba(255,255,255,.12);
        --text: rgba(255,255,255,.92);
        --muted: rgba(148,163,184,.95);
        --cta: #60a5fa;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple Color Emoji", "Segoe UI Emoji";
        background: radial-gradient(1200px 700px at 30% 10%, rgba(139,92,246,.18), transparent 60%),
                    radial-gradient(1000px 600px at 80% 70%, rgba(59,130,246,.22), transparent 60%),
                    var(--bg);
        color: var(--text);
      }}
      .wrap {{
        max-width: 980px;
        margin: 0 auto;
        padding: 32px 16px 64px;
      }}
      .card {{
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 18px;
        background: var(--panel);
      }}
      .row {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 16px;
      }}
      @media (min-width: 860px) {{
        .row {{ grid-template-columns: 1.15fr .85fr; }}
      }}
      .thumb {{
        width: 100%;
        border-radius: 14px;
        border: 1px solid var(--border);
        background: rgba(15,23,42,.65);
      }}
      video {{
        width: 100%;
        border-radius: 14px;
        border: 1px solid var(--border);
        background: rgba(15,23,42,.65);
      }}
      .meta {{
        font-size: 12px;
        color: var(--muted);
        margin-top: 6px;
      }}
      h1 {{
        font-size: 20px;
        margin: 0 0 8px;
      }}
      p {{
        margin: 0;
        color: var(--muted);
        font-size: 14px;
        line-height: 1.5;
      }}
      .cta {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 14px;
        text-decoration: none;
        color: rgba(2,6,23,.95);
        background: var(--cta);
        font-weight: 800;
      }}
      button.cta {{
        font: inherit;
        cursor: pointer;
        border: 0;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 14px;
      }}
      .cta.secondary {{
        background: transparent;
        color: var(--text);
        border: 1px solid var(--border);
      }}
      .tiny {{
        margin-top: 10px;
        font-size: 12px;
        color: rgba(148,163,184,.9);
        word-break: break-all;
      }}
      code {{
        color: rgba(226,232,240,.92);
      }}
      .kit {{
        margin-top: 14px;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: 16px;
        background: rgba(2,6,23,.35);
      }}
      .kitrow {{
        display: flex;
        gap: 12px;
        align-items: flex-start;
      }}
      @media (max-width: 520px) {{
        .kitrow {{ flex-direction: column; }}
      }}
      .qr {{
        width: 164px;
        height: 164px;
        border-radius: 14px;
        border: 1px solid var(--border);
        background: white;
      }}
      .kitcol {{ flex: 1; min-width: 0; }}
      .kitlabel {{ font-size: 12px; color: var(--muted); margin: 0 0 8px; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="row">
        <div class="card">
          {'<video controls playsinline preload=\\"metadata\\" src=\\"' + html.escape(vertical_mp4) + '\\"></video>' if vertical_mp4 else '<img class=\\"thumb\\" src=\\"' + html.escape(og_image) + '\\" alt=\\"Clip thumbnail\\" />'}
        </div>
        <div class="card">
          <h1>{body_title}</h1>
          <p>{body_summary}</p>
          <div class="meta">{html.escape(body_meta)}</div>
          <div class="meta">generated_at: {html.escape(body_date)}</div>
          <div class="meta"><strong>Play in ~30 seconds.</strong> Open, watch, remix, or queue a match.</div>
          <div class="actions">
	            <a class="cta" href="{html.escape(app_url)}">Open in App</a>
	            {install_cta_html}
	            {secondary_ctas_html}
	            <a class="cta secondary" href="{html.escape(ranked_url)}">Go Ranked</a>
	            {download_kit_html}
	            {download_mp4_html}
	          </div>
          <div class="kit">
            <div class="kitlabel"><strong>Scan to open on mobile.</strong> Copy caption for socials.</div>
            <div class="kitrow">
              <img class="qr" src="{html.escape(qr_img)}" alt="QR code" />
              <div class="kitcol">
                <div class="actions">
                  <button class="cta secondary" type="button" onclick="copyText('app_link','Copied app link.','link_copied')">Copy App Link</button>
                  <button class="cta secondary" type="button" onclick="copyText('caption_text','Copied caption.','caption_copied')">Copy Caption</button>
                  <button class="cta secondary" type="button" onclick="copyDiscordMsg()">Copy for Discord</button>
                </div>
                <input type="hidden" id="app_link" value="{html.escape(app_link)}" />
                <input type="hidden" id="discord_msg" value="{html.escape(discord_msg)}" />
                <textarea id="caption_text" style="display:none">{html.escape(caption_text)}</textarea>
                <div class="tiny">app: <code>{html.escape(app_link)}</code></div>
              </div>
            </div>
          </div>
          <div id="copy-status" class="meta"></div>
          <div class="tiny">share: <code>{html.escape(og_url)}</code></div>
          <script>
            const SHARE_SOURCE = "s/clip";
            const SHARE_REF = "{html.escape(str(ref or ""))}";
            const META_BASE = {{
              replay_id: "{html.escape(replay_id)}",
              match_id: "{html.escape(match_id)}",
              share_caption_version: "{SHARE_CAPTION_VERSION}",
              clip_len_variant: "{html.escape(str(clip_len_variant or ""))}",
              captions_version: "{html.escape(str(forced_captions_version or ""))}",
              captions_template_id: "{html.escape(str(forced_template_id or ""))}",
              variants: {{
                clip_len_v1: "{html.escape(str(clip_len_variant or ""))}",
                captions_v2: "{html.escape(str(forced_template_id or ""))}",
              }},
            }};

            function track(type, extra) {{
              try {{
                fetch("/s/track" + (window.location && window.location.search ? window.location.search : ""), {{
                  method: "POST",
                  headers: {{ "content-type": "application/json" }},
                  body: JSON.stringify({{
                    type: type,
                    source: SHARE_SOURCE,
                    ref: SHARE_REF || null,
                    meta: Object.assign({{}}, META_BASE, extra || {{}}),
                  }}),
                }}).catch(function() {{}});
              }} catch (e) {{}}
            }}

            (function() {{
              try {{
                var v = document.querySelector("video");
                if (!v || !v.addEventListener) return;
                var fired = false;
                v.addEventListener("ended", function() {{
                  if (fired) return;
                  fired = true;
                  track("clip_completion", {{ ended: 1 }});
                }});
              }} catch (e) {{}}
            }})();

            function _textFrom(id) {{
              var el = document.getElementById(String(id || ""));
              if (!el) return "";
              try {{
                if (typeof el.value === "string") return String(el.value);
              }} catch (e) {{}}
              try {{
                return String(el.textContent || "");
              }} catch (e) {{}}
              return "";
            }}

            function copyText(id, doneLabel, trackType) {{
              var text = _textFrom(id);
              if (!text) return;
              var done = function() {{
                var s = document.getElementById("copy-status");
                if (!s) return;
                s.textContent = String(doneLabel || "Copied.");
                setTimeout(function() {{ s.textContent = ""; }}, 1800);
              }};
              var ondone = function() {{
                done();
                if (trackType) track(String(trackType), {{}});
                if (trackType === "caption_copied" || trackType === "link_copied") {{
                  track("clip_share", {{ kind: String(trackType) }});
                }}
              }};
              if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text).then(ondone).catch(ondone);
                return;
              }}
              try {{
                var ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                ondone();
              }} catch (e) {{}}
            }}

            function copyDiscordMsg() {{
              copyText("discord_msg", "Copied message for Discord.", "");
            }}
          </script>
        </div>
      </div>
    </div>
  </body>
</html>"""

    return HTMLResponse(content=html_out)


def _sharecard_v2_key(
    *, replay_id: str, digest: str, theme: str = "dark", locale: str = "en"
) -> str:
    safe_digest = (digest or "")[:12] if digest else "unknown"
    return f"sharecards/sharecard_v2_{replay_id}_{safe_digest}_{theme}_{locale}.png"


def _public_asset_or_placeholder(*, key: str | None) -> Response:
    if not key:
        return Response(content=_placeholder_png_bytes(), media_type="image/png")
    backend = get_storage_backend()
    try:
        local = backend.local_path(key=key)
    except Exception:  # noqa: BLE001
        local = None
    if local is not None and local.exists():
        return FileResponse(
            path=str(local), media_type="image/png", filename=local.name
        )
    try:
        if backend.exists(key=key):
            return RedirectResponse(url=backend.public_url(key=key), status_code=307)
    except Exception:  # noqa: BLE001
        pass
    return Response(content=_placeholder_png_bytes(), media_type="image/png")


@router.get("/build/{blueprint_id}/og.png")
def build_og_image(blueprint_id: str) -> Response:
    # Public OG image for build shares. It never 404s.
    ensure_artifacts_dir()
    with SessionLocal() as db:
        bp = db.get(Blueprint, blueprint_id)
        if not bp or bp.status != "submitted":
            return _public_asset_or_placeholder(key=None)

        match = db.scalar(
            select(Match)
            .where(Match.status == "done")
            .where(
                (Match.blueprint_a_id == blueprint_id)
                | (Match.blueprint_b_id == blueprint_id)
            )
            .order_by(desc(Match.finished_at), desc(Match.created_at), Match.id.asc())
            .limit(1)
        )
        if not match:
            return _public_asset_or_placeholder(key=None)
        replay = db.get(Replay, getattr(match, "replay_id", None) or "")  # type: ignore[arg-type]
        if not replay:
            replay = db.scalar(select(Replay).where(Replay.match_id == match.id))
        if not replay:
            return _public_asset_or_placeholder(key=None)

        return _public_asset_or_placeholder(
            key=_sharecard_v2_key(replay_id=replay.id, digest=str(replay.digest or ""))
        )


@router.get("/profile/{user_id}/og.png")
def profile_og_image(user_id: str) -> Response:
    # Public OG image for profile shares. It never 404s.
    ensure_artifacts_dir()
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            return _public_asset_or_placeholder(key=None)

        match = db.scalar(
            select(Match)
            .where(Match.status == "done")
            .where(Match.user_a_id == user_id)
            .order_by(desc(Match.finished_at), desc(Match.created_at), Match.id.asc())
            .limit(1)
        )
        if not match:
            return _public_asset_or_placeholder(key=None)

        replay = db.scalar(select(Replay).where(Replay.match_id == match.id))
        if not replay:
            return _public_asset_or_placeholder(key=None)

        return _public_asset_or_placeholder(
            key=_sharecard_v2_key(replay_id=replay.id, digest=str(replay.digest or ""))
        )


@router.get("/build/{blueprint_id}", response_class=HTMLResponse)
def build_landing(
    blueprint_id: str, request: Request, ref: str | None = None
) -> HTMLResponse:
    base = _abs_base(request)

    with SessionLocal() as db:
        bp = db.get(Blueprint, blueprint_id)
        if not bp or bp.status != "submitted":
            raise HTTPException(status_code=404, detail="Build not found")
        u = db.get(User, bp.user_id)
        bp_name = str(bp.name)

        try:
            log_event(
                db,
                type="share_open",
                user_id=None,
                request=request,
                payload={
                    "source": "s/build",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "blueprint_id": blueprint_id,
                    "creator_user_id": bp.user_id,
                    "mode": str(bp.mode or ""),
                    "ruleset_version": str(bp.ruleset_version or ""),
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            log_event(
                db,
                type="qr_shown",
                user_id=None,
                request=request,
                payload={
                    "source": "s/build",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "blueprint_id": blueprint_id,
                    "creator_user_id": bp.user_id,
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            db.commit()
        except Exception:  # noqa: BLE001
            pass

        creator = u.display_name if u else "Lab_Unknown"
        mode = str(bp.mode or "")
        ruleset = str(bp.ruleset_version or Settings().ruleset_version)
        build_code = str(bp.build_code or "").strip()
        if not build_code:
            try:
                spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
                pack_hash: str | None = None
                try:
                    from neuroleague_sim.pack_loader import active_pack_hash

                    pack_hash = active_pack_hash()
                except Exception:  # noqa: BLE001
                    pack_hash = None
                build_code = encode_build_code(spec=spec, pack_hash=pack_hash)
            except Exception:  # noqa: BLE001
                build_code = ""

    og_url = f"{base}/s/build/{blueprint_id}"
    if ref:
        og_url += f"?ref={quote(str(ref), safe='')}"
    og_image = f"{base}/s/build/{blueprint_id}/og.png"
    og_image_w, og_image_h = 1200, 630
    if build_code:
        app_url = _start_href(
            next_path=f"/forge?import={build_code}", ref=ref, src="s/build"
        )
    else:
        app_url = _start_href(next_path="/gallery", ref=ref, src="s/build")

    title = f"NeuroLeague Build — {bp_name}"
    description = f"{creator} · {mode} · {ruleset}"
    discord_msg = f"30s Lab Build: {bp_name} — {og_url}"

    if build_code:
        import_next = f"/forge?import={build_code}"
        import_url = _start_href(next_path=import_next, ref=ref, src="s/build_import")
        quick_url = _start_href(
            next_path=f"/quick?import={build_code}&mode={mode}",
            ref=ref,
            src="s/build_quick",
        )
    else:
        import_next = "/gallery"
        import_url = _start_href(next_path=import_next, ref=ref, src="s/build_import")
        quick_url = None

    caption_text = build_share_caption(
        build_name=bp_name,
        creator_name=creator,
        mode=mode,
        ruleset=ruleset,
        cta="Remix This",
    )
    qr_url = _start_href(next_path=import_next, ref=ref, src="s/build_qr")
    app_link = f"{base}{qr_url}"
    qr_img = f"{base}/s/qr.png?next={quote(import_next, safe='')}&src=s/build_qr&scale=6"
    if ref:
        qr_img += f"&ref={quote(str(ref), safe='')}"

    html_out = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <meta property="og:title" content="{html.escape(title)}" />
    <meta property="og:description" content="{html.escape(description)}" />
    <meta property="og:image" content="{html.escape(og_image)}" />
    <meta property="og:image:secure_url" content="{html.escape(og_image)}" />
    <meta property="og:image:width" content="{og_image_w}" />
    <meta property="og:image:height" content="{og_image_h}" />
    <meta property="og:image:alt" content="NeuroLeague build preview" />
    <meta property="og:url" content="{html.escape(og_url)}" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{html.escape(title)}" />
    <meta name="twitter:description" content="{html.escape(description)}" />
    <meta name="twitter:image" content="{html.escape(og_image)}" />
    <meta name="twitter:image:alt" content="NeuroLeague build preview" />
    <style>
      :root {{
        --bg: #0f172a;
        --panel: rgba(2,6,23,.55);
        --border: rgba(255,255,255,.12);
        --text: rgba(255,255,255,.92);
        --muted: rgba(148,163,184,.95);
        --cta: #60a5fa;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        background: radial-gradient(1200px 700px at 30% 10%, rgba(139,92,246,.18), transparent 60%),
                    radial-gradient(1000px 600px at 80% 70%, rgba(59,130,246,.22), transparent 60%),
                    var(--bg);
        color: var(--text);
      }}
      .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }}
      .card {{ border: 1px solid var(--border); border-radius: 20px; padding: 18px; background: var(--panel); }}
      .row {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
      @media (min-width: 860px) {{ .row {{ grid-template-columns: 1.15fr .85fr; }} }}
      img {{ width: 100%; border-radius: 14px; border: 1px solid var(--border); background: rgba(15,23,42,.65); }}
      h1 {{ font-size: 20px; margin: 0 0 8px; }}
      p {{ margin: 0; color: var(--muted); font-size: 14px; line-height: 1.5; }}
      .meta {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
      .cta {{
        display: inline-flex; align-items: center; justify-content: center; gap: 10px;
        padding: 10px 14px; border-radius: 14px;
        text-decoration: none; color: rgba(2,6,23,.95); background: var(--cta); font-weight: 800;
      }}
      button.cta {{
        font: inherit;
        cursor: pointer;
        border: 0;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 14px;
      }}
      .cta.secondary {{
        background: transparent;
        color: var(--text);
        border: 1px solid var(--border);
      }}
      .tiny {{ margin-top: 10px; font-size: 12px; color: rgba(148,163,184,.9); word-break: break-all; }}
      code {{ color: rgba(226,232,240,.92); }}
      .kit {{
        margin-top: 14px;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: 16px;
        background: rgba(2,6,23,.35);
      }}
      .kitrow {{
        display: flex;
        gap: 12px;
        align-items: flex-start;
      }}
      @media (max-width: 520px) {{
        .kitrow {{ flex-direction: column; }}
      }}
      .qr {{
        width: 164px;
        height: 164px;
        border-radius: 14px;
        border: 1px solid var(--border);
        background: white;
      }}
      .kitcol {{ flex: 1; min-width: 0; }}
      .kitlabel {{ font-size: 12px; color: var(--muted); margin: 0 0 8px; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="row">
        <div class="card">
          <img src="{html.escape(og_image)}" alt="Build preview" />
        </div>
        <div class="card">
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(description)}</p>
          <div class="meta">{html.escape(mode)} · {html.escape(ruleset)}</div>
          {f'<div class="tiny">Build Code: <code>{html.escape(build_code)}</code></div>' if build_code else ""}
          <div class="meta"><strong>Play in ~30 seconds.</strong> Fork this build and queue a match.</div>
          <div class="actions">
            <a class="cta" href="{html.escape(import_url)}">Remix This Build</a>
            {f'<a class="cta secondary" href="{html.escape(quick_url)}">Quick Battle</a>' if quick_url else ""}
          </div>
          <div class="kit">
            <div class="kitlabel"><strong>Scan to open on mobile.</strong> Copy caption for socials.</div>
            <div class="kitrow">
              <img class="qr" src="{html.escape(qr_img)}" alt="QR code" />
              <div class="kitcol">
                <div class="actions">
                  <button class="cta secondary" type="button" onclick="copyText('app_link','Copied app link.','link_copied')">Copy App Link</button>
                  {"""<button class="cta secondary" type="button" onclick="copyText('build_code','Copied build code.','link_copied')">Copy Build Code</button>""" if build_code else ""}
                  <button class="cta secondary" type="button" onclick="copyText('caption_text','Copied caption.','caption_copied')">Copy Caption</button>
                  <button class="cta secondary" type="button" onclick="copyDiscordMsg()">Copy for Discord</button>
                </div>
                <input type="hidden" id="app_link" value="{html.escape(app_link)}" />
                <input type="hidden" id="build_code" value="{html.escape(build_code)}" />
                <input type="hidden" id="discord_msg" value="{html.escape(discord_msg)}" />
                <textarea id="caption_text" style="display:none">{html.escape(caption_text)}</textarea>
                <div class="tiny">app: <code>{html.escape(app_link)}</code></div>
                {f'<div class="tiny">code: <code>{html.escape(build_code)}</code></div>' if build_code else ""}
              </div>
            </div>
          </div>
          <div id="copy-status" class="meta"></div>
          <div class="tiny">share: <code>{html.escape(og_url)}</code></div>
          <script>
            const SHARE_SOURCE = "s/build";
            const SHARE_REF = "{html.escape(str(ref or ""))}";
            const META_BASE = {{
              blueprint_id: "{html.escape(blueprint_id)}",
              share_caption_version: "{SHARE_CAPTION_VERSION}",
            }};

            function track(type, extra) {{
              try {{
                fetch("/s/track" + (window.location && window.location.search ? window.location.search : ""), {{
                  method: "POST",
                  headers: {{ "content-type": "application/json" }},
                  body: JSON.stringify({{
                    type: type,
                    source: SHARE_SOURCE,
                    ref: SHARE_REF || null,
                    meta: Object.assign({{}}, META_BASE, extra || {{}}),
                  }}),
                }}).catch(function() {{}});
              }} catch (e) {{}}
            }}

            function _textFrom(id) {{
              var el = document.getElementById(String(id || ""));
              if (!el) return "";
              try {{
                if (typeof el.value === "string") return String(el.value);
              }} catch (e) {{}}
              try {{
                return String(el.textContent || "");
              }} catch (e) {{}}
              return "";
            }}

            function copyText(id, doneLabel, trackType) {{
              var text = _textFrom(id);
              if (!text) return;
              var done = function() {{
                var s = document.getElementById("copy-status");
                if (!s) return;
                s.textContent = String(doneLabel || "Copied.");
                setTimeout(function() {{ s.textContent = ""; }}, 1800);
              }};
              var ondone = function() {{
                done();
                if (trackType) track(String(trackType), {{}});
              }};
              if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text).then(ondone).catch(ondone);
                return;
              }}
              try {{
                var ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                ondone();
              }} catch (e) {{}}
            }}

            function copyDiscordMsg() {{
              copyText("discord_msg", "Copied message for Discord.", "");
            }}
          </script>
        </div>
      </div>
    </div>
  </body>
</html>"""

    return HTMLResponse(content=html_out)


@router.get("/profile/{user_id}", response_class=HTMLResponse)
def profile_landing(
    user_id: str,
    request: Request,
    mode: Literal["1v1", "team"] = "1v1",
    ref: str | None = None,
) -> HTMLResponse:
    base = _abs_base(request)
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail="Profile not found")
        display_name = str(u.display_name)
        user_id_str = str(u.id)
        r = db.get(Rating, {"user_id": user_id, "mode": mode})
        elo = int(r.elo) if r else 1000
        games = int(r.games_played) if r else 0
        best_match_id: str | None = None
        best_replay_id: str | None = None
        best_start_sec: float | None = None
        best_end_sec: float | None = None

        try:
            m = db.scalar(
                select(Match)
                .where(Match.status == "done")
                .where(Match.user_a_id == user_id)
                .where(Match.mode == mode)
                .order_by(desc(Match.finished_at), desc(Match.created_at), Match.id.asc())
                .limit(1)
            )
            if m:
                replay = db.scalar(select(Replay).where(Replay.match_id == m.id))
                if replay:
                    from neuroleague_api.clip_render import best_clip_segment

                    payload = load_replay_json(artifact_path=replay.artifact_path)
                    st, et = best_clip_segment(payload, max_duration_sec=12.0)
                    best_match_id = str(m.id)
                    best_replay_id = str(replay.id)
                    best_start_sec = float(st) / 20.0
                    best_end_sec = float(et) / 20.0
        except Exception:  # noqa: BLE001
            best_match_id = None
            best_replay_id = None
            best_start_sec = None
            best_end_sec = None

        try:
            log_event(
                db,
                type="share_open",
                user_id=None,
                request=request,
                payload={
                    "source": "s/profile",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "profile_user_id": user_id,
                    "mode": str(mode or ""),
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            log_event(
                db,
                type="qr_shown",
                user_id=None,
                request=request,
                payload={
                    "source": "s/profile",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "profile_user_id": user_id,
                    "mode": str(mode or ""),
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            db.commit()
        except Exception:  # noqa: BLE001
            pass

    og_url = f"{base}/s/profile/{user_id}?mode={mode}"
    if ref:
        og_url += f"&ref={quote(str(ref), safe='')}"
    og_image = f"{base}/s/profile/{user_id}/og.png"
    og_image_w, og_image_h = 1200, 630
    next_path = f"/profile/{user_id}?mode={mode}"
    follow_url = _start_href(next_path=next_path, ref=ref, src="s/profile_follow")

    bestclip_url = follow_url
    if best_match_id and best_start_sec is not None and best_end_sec is not None:
        q = f"t={best_start_sec:.1f}&end={best_end_sec:.1f}"
        bestclip_url = _start_href(
            next_path=f"/replay/{best_match_id}?{q}",
            ref=ref,
            src="s/profile_bestclip",
        )

    build_of_day_url = _start_href(next_path="/home", ref=ref, src="s/profile_bod")

    title = f"NeuroLeague Profile — {display_name}"
    description = f"Elo {elo} · games {games} · mode {mode}"
    discord_msg = f"30s Lab Profile: {display_name} — {og_url}"

    caption_text = profile_share_caption(display_name=display_name, cta="Follow")
    qr_url = _start_href(next_path=next_path, ref=ref, src="s/profile_qr")
    app_link = f"{base}{qr_url}"
    qr_img = f"{base}/s/qr.png?next={quote(next_path, safe='')}&src=s/profile_qr&scale=6"
    if ref:
        qr_img += f"&ref={quote(str(ref), safe='')}"

    html_out = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <meta property="og:title" content="{html.escape(title)}" />
    <meta property="og:description" content="{html.escape(description)}" />
    <meta property="og:image" content="{html.escape(og_image)}" />
    <meta property="og:image:secure_url" content="{html.escape(og_image)}" />
    <meta property="og:image:width" content="{og_image_w}" />
    <meta property="og:image:height" content="{og_image_h}" />
    <meta property="og:image:alt" content="NeuroLeague profile preview" />
    <meta property="og:url" content="{html.escape(og_url)}" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{html.escape(title)}" />
    <meta name="twitter:description" content="{html.escape(description)}" />
    <meta name="twitter:image" content="{html.escape(og_image)}" />
    <meta name="twitter:image:alt" content="NeuroLeague profile preview" />
    <style>
      :root {{
        --bg: #0f172a;
        --panel: rgba(2,6,23,.55);
        --border: rgba(255,255,255,.12);
        --text: rgba(255,255,255,.92);
        --muted: rgba(148,163,184,.95);
        --cta: #60a5fa;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        background: radial-gradient(1200px 700px at 30% 10%, rgba(139,92,246,.18), transparent 60%),
                    radial-gradient(1000px 600px at 80% 70%, rgba(59,130,246,.22), transparent 60%),
                    var(--bg);
        color: var(--text);
      }}
      .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }}
      .card {{ border: 1px solid var(--border); border-radius: 20px; padding: 18px; background: var(--panel); }}
      img {{ width: 100%; border-radius: 14px; border: 1px solid var(--border); background: rgba(15,23,42,.65); }}
      h1 {{ font-size: 20px; margin: 0 0 8px; }}
      p {{ margin: 0; color: var(--muted); font-size: 14px; line-height: 1.5; }}
      .meta {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
      .cta {{
        display: inline-flex; align-items: center; justify-content: center; gap: 10px;
        padding: 10px 14px; border-radius: 14px;
        text-decoration: none; color: rgba(2,6,23,.95); background: var(--cta); font-weight: 800;
      }}
      button.cta {{
        font: inherit;
        cursor: pointer;
        border: 0;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 14px;
      }}
      .cta.secondary {{
        background: transparent;
        color: var(--text);
        border: 1px solid var(--border);
      }}
      .tiny {{ margin-top: 10px; font-size: 12px; color: rgba(148,163,184,.9); word-break: break-all; }}
      code {{ color: rgba(226,232,240,.92); }}
      .kit {{
        margin-top: 14px;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: 16px;
        background: rgba(2,6,23,.35);
      }}
      .kitrow {{
        display: flex;
        gap: 12px;
        align-items: flex-start;
      }}
      @media (max-width: 520px) {{
        .kitrow {{ flex-direction: column; }}
      }}
      .qr {{
        width: 164px;
        height: 164px;
        border-radius: 14px;
        border: 1px solid var(--border);
        background: white;
      }}
      .kitcol {{ flex: 1; min-width: 0; }}
      .kitlabel {{ font-size: 12px; color: var(--muted); margin: 0 0 8px; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <img src="{html.escape(og_image)}" alt="Profile preview" />
        <h1 style="margin-top: 14px;">{html.escape(title)}</h1>
        <p>{html.escape(description)}</p>
        <div class="meta">{html.escape(user_id_str)}</div>
        <div class="meta"><strong>Play in ~30 seconds.</strong> Follow, watch clips, and challenge builds.</div>
        <div class="actions">
          <a class="cta" href="{html.escape(follow_url)}">Follow</a>
          <a class="cta secondary" href="{html.escape(bestclip_url)}">Watch Best Clip</a>
          <a class="cta secondary" href="{html.escape(build_of_day_url)}">Try Build of the Day</a>
        </div>
        <div class="kit">
          <div class="kitlabel"><strong>Scan to open on mobile.</strong> Copy caption for socials.</div>
          <div class="kitrow">
            <img class="qr" src="{html.escape(qr_img)}" alt="QR code" />
            <div class="kitcol">
              <div class="actions">
                <button class="cta secondary" type="button" onclick="copyText('app_link','Copied app link.','link_copied')">Copy App Link</button>
                <button class="cta secondary" type="button" onclick="copyText('caption_text','Copied caption.','caption_copied')">Copy Caption</button>
                <button class="cta secondary" type="button" onclick="copyDiscordMsg()">Copy for Discord</button>
              </div>
              <input type="hidden" id="app_link" value="{html.escape(app_link)}" />
              <input type="hidden" id="discord_msg" value="{html.escape(discord_msg)}" />
              <textarea id="caption_text" style="display:none">{html.escape(caption_text)}</textarea>
              <div class="tiny">app: <code>{html.escape(app_link)}</code></div>
            </div>
          </div>
        </div>
        <div id="copy-status" class="meta"></div>
        <div class="tiny">share: <code>{html.escape(og_url)}</code></div>
        <script>
          const SHARE_SOURCE = "s/profile";
          const SHARE_REF = "{html.escape(str(ref or ""))}";
          const META_BASE = {{
            profile_user_id: "{html.escape(user_id)}",
            mode: "{html.escape(str(mode))}",
            best_replay_id: "{html.escape(str(best_replay_id or ""))}",
            share_caption_version: "{SHARE_CAPTION_VERSION}",
          }};

          function track(type, extra) {{
            try {{
              fetch("/s/track" + (window.location && window.location.search ? window.location.search : ""), {{
                method: "POST",
                headers: {{ "content-type": "application/json" }},
                body: JSON.stringify({{
                  type: type,
                  source: SHARE_SOURCE,
                  ref: SHARE_REF || null,
                  meta: Object.assign({{}}, META_BASE, extra || {{}}),
                }}),
              }}).catch(function() {{}});
            }} catch (e) {{}}
          }}

          function _textFrom(id) {{
            var el = document.getElementById(String(id || ""));
            if (!el) return "";
            try {{
              if (typeof el.value === "string") return String(el.value);
            }} catch (e) {{}}
            try {{
              return String(el.textContent || "");
            }} catch (e) {{}}
            return "";
          }}

          function copyText(id, doneLabel, trackType) {{
            var text = _textFrom(id);
            if (!text) return;
            var done = function() {{
              var s = document.getElementById("copy-status");
              if (!s) return;
              s.textContent = String(doneLabel || "Copied.");
              setTimeout(function() {{ s.textContent = ""; }}, 1800);
            }};
            var ondone = function() {{
              done();
              if (trackType) track(String(trackType), {{}});
            }};
            if (navigator.clipboard && navigator.clipboard.writeText) {{
              navigator.clipboard.writeText(text).then(ondone).catch(ondone);
              return;
            }}
            try {{
              var ta = document.createElement("textarea");
              ta.value = text;
              document.body.appendChild(ta);
              ta.select();
              document.execCommand("copy");
              document.body.removeChild(ta);
              ondone();
            }} catch (e) {{}}
          }}

          function copyDiscordMsg() {{
            copyText("discord_msg", "Copied message for Discord.", "");
          }}
        </script>
      </div>
    </div>
  </body>
</html>"""

    return HTMLResponse(content=html_out)


@router.get("/challenge/{challenge_id}", response_class=HTMLResponse)
def challenge_landing(
    challenge_id: str,
    request: Request,
    ref: str | None = None,
) -> HTMLResponse:
    base = _abs_base(request)

    kind = "build"
    mode = "1v1"
    ruleset = Settings().ruleset_version
    portal_id: str | None = None
    title = f"NeuroLeague Challenge — {challenge_id}"
    description = "Beat this build in NeuroLeague."
    og_url = f"{base}/s/challenge/{challenge_id}"
    if ref:
        og_url += f"?ref={quote(str(ref), safe='')}"
    og_image = f"{base}/s/clip/unknown/thumb.png"  # fallback, never used in practice
    og_image_w, og_image_h = 1200, 630
    app_url = _start_href(
        next_path=f"/challenge/{challenge_id}", ref=ref, src="s/challenge"
    )

    with SessionLocal() as db:
        ch = db.get(Challenge, challenge_id)
        if not ch:
            raise HTTPException(status_code=404, detail="Challenge not found")

        kind = str(ch.kind or "build")
        mode = str(ch.mode or "1v1")
        ruleset = str(ch.ruleset_version or ruleset)
        portal_id = str(ch.portal_id or "") or None

        if ch.target_replay_id:
            s = float(ch.start_sec or 0.0)
            e = float(ch.end_sec) if ch.end_sec is not None else None
            q = f"start={s:.1f}"
            if e is not None:
                q += f"&end={e:.1f}"
            og_image = (
                f"{base}/s/clip/{ch.target_replay_id}/thumb.png?{q}&scale=1&theme=dark"
            )
        elif ch.target_blueprint_id:
            bp = db.get(Blueprint, ch.target_blueprint_id)
            if bp and bp.status == "submitted":
                title = f"Beat This Build — {bp.name}"
                description = f"{bp.name} · {mode} · {ruleset}"
            og_image = f"{base}/s/build/{ch.target_blueprint_id}/og.png"
        else:
            og_image = f"{base}/s/clip/{challenge_id}/thumb.png?start=0.0&end=6.0&scale=1&theme=dark"

        title = title if title else f"NeuroLeague Challenge — {challenge_id}"
        if kind == "clip":
            title = f"Beat This Clip — {challenge_id}"
            description = f"{mode} · {ruleset}"
        if portal_id:
            description = f"{description} · portal {portal_id}"

        try:
            log_event(
                db,
                type="share_open",
                user_id=None,
                request=request,
                payload={
                    "source": "s/challenge",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "challenge_id": challenge_id,
                    "kind": kind,
                    "mode": mode,
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            log_event(
                db,
                type="qr_shown",
                user_id=None,
                request=request,
                payload={
                    "source": "s/challenge",
                    "ref": ref,
                    "platform": _platform_guess(request),
                    "challenge_id": challenge_id,
                    "kind": kind,
                    "mode": mode,
                    "share_caption_version": SHARE_CAPTION_VERSION,
                },
            )
            db.commit()
        except Exception:  # noqa: BLE001
            pass

    body_title = html.escape(title)
    body_desc = html.escape(description)
    discord_msg = f"30s Lab Challenge: {title} — {og_url}"

    caption_text = challenge_share_caption(title=title, portal_id=portal_id, cta="Beat This")
    qr_next_path = f"/challenge/{challenge_id}"
    qr_url = _start_href(next_path=qr_next_path, ref=ref, src="s/challenge_qr")
    app_link = f"{base}{qr_url}"
    qr_img = (
        f"{base}/s/qr.png?next={quote(qr_next_path, safe='')}&src=s/challenge_qr&scale=6"
    )
    if ref:
        qr_img += f"&ref={quote(str(ref), safe='')}"

    html_out = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <meta property="og:title" content="{html.escape(title)}" />
    <meta property="og:description" content="{html.escape(description)}" />
    <meta property="og:image" content="{html.escape(og_image)}" />
    <meta property="og:image:secure_url" content="{html.escape(og_image)}" />
    <meta property="og:image:width" content="{og_image_w}" />
    <meta property="og:image:height" content="{og_image_h}" />
    <meta property="og:image:alt" content="NeuroLeague challenge preview" />
    <meta property="og:url" content="{html.escape(og_url)}" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{html.escape(title)}" />
    <meta name="twitter:description" content="{html.escape(description)}" />
    <meta name="twitter:image" content="{html.escape(og_image)}" />
    <meta name="twitter:image:alt" content="NeuroLeague challenge preview" />
    <style>
      :root {{
        --bg: #0f172a;
        --panel: rgba(2,6,23,.55);
        --border: rgba(255,255,255,.12);
        --text: rgba(255,255,255,.92);
        --muted: rgba(148,163,184,.95);
        --cta: #22c55e;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        background: radial-gradient(1200px 700px at 30% 10%, rgba(34,197,94,.18), transparent 60%),
                    radial-gradient(1000px 600px at 80% 70%, rgba(59,130,246,.18), transparent 60%),
                    var(--bg);
        color: var(--text);
      }}
      .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }}
      .row {{ display: grid; grid-template-columns: 1fr; gap: 16px; }}
      @media (min-width: 860px) {{ .row {{ grid-template-columns: 1.15fr .85fr; }} }}
      .card {{ border: 1px solid var(--border); border-radius: 20px; padding: 18px; background: var(--panel); }}
      img {{ width: 100%; border-radius: 14px; border: 1px solid var(--border); background: rgba(15,23,42,.65); }}
      h1 {{ font-size: 20px; margin: 0 0 8px; }}
      p {{ margin: 0; color: var(--muted); font-size: 14px; line-height: 1.5; }}
      .meta {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
      .cta {{
        display: inline-flex; align-items: center; justify-content: center; gap: 10px;
        padding: 10px 14px; border-radius: 14px;
        text-decoration: none; color: rgba(2,6,23,.95); background: var(--cta); font-weight: 900;
      }}
      button.cta {{
        font: inherit;
        cursor: pointer;
        border: 0;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 14px;
      }}
      .cta.secondary {{
        background: transparent;
        color: var(--text);
        border: 1px solid var(--border);
        font-weight: 900;
      }}
      .tiny {{ margin-top: 10px; font-size: 12px; color: rgba(148,163,184,.9); word-break: break-all; }}
      code {{ color: rgba(226,232,240,.92); }}
      .kit {{
        margin-top: 14px;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: 16px;
        background: rgba(2,6,23,.35);
      }}
      .kitrow {{
        display: flex;
        gap: 12px;
        align-items: flex-start;
      }}
      @media (max-width: 520px) {{
        .kitrow {{ flex-direction: column; }}
      }}
      .qr {{
        width: 164px;
        height: 164px;
        border-radius: 14px;
        border: 1px solid var(--border);
        background: white;
      }}
      .kitcol {{ flex: 1; min-width: 0; }}
      .kitlabel {{ font-size: 12px; color: var(--muted); margin: 0 0 8px; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="row">
        <div class="card">
          <img src="{html.escape(og_image)}" alt="Challenge preview" />
        </div>
        <div class="card">
          <h1>{body_title}</h1>
          <p>{body_desc}</p>
          <div class="meta">{html.escape(mode)} · {html.escape(ruleset)}</div>
          <div class="meta"><strong>Play in ~30 seconds.</strong> Beat this and share your win.</div>
          <div class="actions">
            <a class="cta" href="{html.escape(app_url)}">Beat This</a>
          </div>
          <div class="kit">
            <div class="kitlabel"><strong>Scan to open on mobile.</strong> Copy caption for socials.</div>
            <div class="kitrow">
              <img class="qr" src="{html.escape(qr_img)}" alt="QR code" />
              <div class="kitcol">
                <div class="actions">
                  <button class="cta secondary" type="button" onclick="copyText('app_link','Copied app link.','link_copied')">Copy App Link</button>
                  <button class="cta secondary" type="button" onclick="copyText('caption_text','Copied caption.','caption_copied')">Copy Caption</button>
                  <button class="cta secondary" type="button" onclick="copyDiscordMsg()">Copy for Discord</button>
                </div>
                <input type="hidden" id="app_link" value="{html.escape(app_link)}" />
                <input type="hidden" id="discord_msg" value="{html.escape(discord_msg)}" />
                <textarea id="caption_text" style="display:none">{html.escape(caption_text)}</textarea>
                <div class="tiny">app: <code>{html.escape(app_link)}</code></div>
              </div>
            </div>
          </div>
          <div id="copy-status" class="meta"></div>
          <div class="tiny">share: <code>{html.escape(og_url)}</code></div>
          <script>
            const SHARE_SOURCE = "s/challenge";
            const SHARE_REF = "{html.escape(str(ref or ""))}";
            const META_BASE = {{
              challenge_id: "{html.escape(challenge_id)}",
              kind: "{html.escape(kind)}",
              mode: "{html.escape(mode)}",
              share_caption_version: "{SHARE_CAPTION_VERSION}",
            }};

            function track(type, extra) {{
              try {{
                fetch("/s/track" + (window.location && window.location.search ? window.location.search : ""), {{
                  method: "POST",
                  headers: {{ "content-type": "application/json" }},
                  body: JSON.stringify({{
                    type: type,
                    source: SHARE_SOURCE,
                    ref: SHARE_REF || null,
                    meta: Object.assign({{}}, META_BASE, extra || {{}}),
                  }}),
                }}).catch(function() {{}});
              }} catch (e) {{}}
            }}

            function _textFrom(id) {{
              var el = document.getElementById(String(id || ""));
              if (!el) return "";
              try {{
                if (typeof el.value === "string") return String(el.value);
              }} catch (e) {{}}
              try {{
                return String(el.textContent || "");
              }} catch (e) {{}}
              return "";
            }}

            function copyText(id, doneLabel, trackType) {{
              var text = _textFrom(id);
              if (!text) return;
              var done = function() {{
                var s = document.getElementById("copy-status");
                if (!s) return;
                s.textContent = String(doneLabel || "Copied.");
                setTimeout(function() {{ s.textContent = ""; }}, 1800);
              }};
              var ondone = function() {{
                done();
                if (trackType) track(String(trackType), {{}});
              }};
              if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(text).then(ondone).catch(ondone);
                return;
              }}
              try {{
                var ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                ondone();
              }} catch (e) {{}}
            }}

            function copyDiscordMsg() {{
              copyText("discord_msg", "Copied message for Discord.", "");
            }}
          </script>
        </div>
      </div>
    </div>
  </body>
</html>"""

    return HTMLResponse(content=html_out)
