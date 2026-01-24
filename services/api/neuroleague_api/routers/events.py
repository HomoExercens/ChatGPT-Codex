from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import orjson
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import ip_hash_from_request, user_agent_hash_from_request
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import Match, Notification, Replay, User
from neuroleague_api.rate_limit import check_rate_limit_dual

router = APIRouter(prefix="/api/events", tags=["events"])


EventType = Literal[
    # Growth funnel.
    "share_open",
    "qr_shown",
    "qr_scanned_click",
    "start_click",
    "caption_copied",
    "bestclip_downloaded",
    "guest_start_success",
    "first_match_queued",
    "first_match_done",
    "first_replay_open",
    "replay_open",
    "blueprint_fork",
    # Mega-hit FTUE (mobile).
    "play_open",
    "ftue_completed",
    # Playtest / Seed Pack.
    "playtest_opened",
    "playtest_step_completed",
    "playtest_completed",
    # Remix flywheel v1.
    "fork_click",
    "fork_created",
    "lineage_viewed",
    # Remix flywheel v2 (reply-chain).
    "beat_this_click",
    "challenge_created",
    "reply_clip_created",
    "reply_clip_shared",
    # Remix flywheel v3.
    "reaction_click",
    "notification_opened",
    "quick_remix_click",
    "quick_remix_selected",
    "quick_remix_applied",
    "auto_tune_click",
    "auto_tune_success",
    "blueprint_submit",
    "ranked_queue",
    "ranked_done",
    "tournament_queue",
    "tournament_done",
    # Clips.
    "clip_view",
    "clip_like",
    "clip_share",
    "clip_remix_click",
    "clip_open_ranked",
    "clip_completion",
    # Experiments.
    "experiment_exposed",
    "experiment_converted",
    # Demo mode.
    "demo_run_start",
    "demo_run_done",
    "demo_kit_download",
    "demo_beat_this_click",
    # Steam demo conversion.
    "wishlist_click",
    "discord_click",
    # Android wrapper.
    "app_open_deeplink",
]


class TrackEventRequest(BaseModel):
    type: EventType
    source: str | None = Field(default=None, max_length=64)
    ref: str | None = Field(default=None, max_length=80)
    utm: dict[str, str] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class TrackEventResponse(BaseModel):
    ok: bool = True


class TrackPublicEventRequest(BaseModel):
    type: Literal["app_open_deeplink"]
    url: str = Field(..., max_length=4096)
    source: str | None = Field(default=None, max_length=64)
    ref: str | None = Field(default=None, max_length=80)
    utm: dict[str, str] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


@router.post("", response_model=TrackEventResponse, include_in_schema=False)
def track_public(
    req: TrackPublicEventRequest,
    request: Request,
    db: Session = DBSession,
) -> TrackEventResponse:
    settings = Settings()
    anon_seed = (
        f"{ip_hash_from_request(request) or ''}|{user_agent_hash_from_request(request) or ''}"
    )
    anon_id = hashlib.sha256(anon_seed.encode("utf-8")).hexdigest()
    check_rate_limit_dual(
        user_id=f"anon:{anon_id[:48]}",
        request=request,
        action="events_track_public",
        per_minute_user=int(settings.rate_limit_events_track_per_minute),
        per_hour_user=int(settings.rate_limit_events_track_per_hour),
        per_minute_ip=int(settings.rate_limit_events_track_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_events_track_per_hour_ip),
        extra_detail={"type": req.type},
    )

    meta: dict[str, Any] = dict(req.meta or {})
    deeplink_query: dict[str, str] = {}
    try:
        parsed = urlparse(str(req.url))
        meta.setdefault("deeplink_scheme", str(parsed.scheme or "")[:32])
        meta.setdefault("deeplink_host", str(parsed.netloc or "")[:160])
        meta.setdefault("deeplink_path", str(parsed.path or "")[:800])
        if parsed.query:
            q = parse_qs(parsed.query, keep_blank_values=False)
            deeplink_query = {
                str(k)[:64]: str((v[0] if v else "") or "")[:200]
                for k, v in q.items()
            }
            meta.setdefault("deeplink_query", deeplink_query)
    except Exception:  # noqa: BLE001
        pass

    utm: dict[str, str] = {}
    try:
        for k, v in (req.utm or {}).items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                utm[str(k)[:40]] = str(v).strip()[:120]
    except Exception:  # noqa: BLE001
        utm = {}

    for k in (
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
    ):
        if k in utm:
            continue
        v = str(deeplink_query.get(k) or "").strip()
        if v:
            utm[k] = v[:120]

    variants: dict[str, str] = {}
    lenv = str(deeplink_query.get("lenv") or "").strip()
    if lenv:
        variants["clip_len_v1"] = lenv[:16]
    ctpl = str(deeplink_query.get("ctpl") or "").strip()
    if ctpl:
        variants["captions_v2"] = ctpl[:64]
    cv = str(deeplink_query.get("cv") or "").strip()

    payload: dict[str, Any] = {
        "source": req.source,
        "ref": req.ref,
        "utm": utm,
        "meta": meta,
        "url": req.url,
        "variants": variants,
        "captions_version": cv[:32] if cv else None,
    }
    log_event(db, type=req.type, user_id=None, request=request, payload=payload)
    db.commit()
    return TrackEventResponse(ok=True)


@router.post("/track", response_model=TrackEventResponse)
def track(
    req: TrackEventRequest,
    request: Request,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> TrackEventResponse:
    # Keep a soft rate limit even in dev: events can be spammed accidentally.
    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="events_track",
        per_minute_user=int(settings.rate_limit_events_track_per_minute),
        per_hour_user=int(settings.rate_limit_events_track_per_hour),
        per_minute_ip=int(settings.rate_limit_events_track_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_events_track_per_hour_ip),
        extra_detail={"type": req.type},
    )

    payload: dict[str, Any] = {
        "source": req.source,
        "ref": req.ref,
        "utm": req.utm,
        "meta": req.meta,
    }
    ev = log_event(db, type=req.type, user_id=user_id, request=request, payload=payload)

    # In-app notification hooks (best-effort).
    if str(req.type) == "reply_clip_shared":
        try:
            meta = req.meta if isinstance(req.meta, dict) else {}
            reply_replay_id = str(meta.get("reply_replay_id") or "").strip()
            parent_replay_id = str(
                meta.get("parent_replay_id") or meta.get("replay_id") or ""
            ).strip()
            match_id = str(meta.get("match_id") or "").strip()
            if reply_replay_id and parent_replay_id:
                parent_replay = db.get(Replay, parent_replay_id)
                parent_match = (
                    db.get(Match, parent_replay.match_id) if parent_replay else None
                )
                recipient = (
                    str(getattr(parent_match, "user_a_id", "") or "")
                    if parent_match
                    else ""
                )
                if recipient and not recipient.startswith("guest_"):
                    dedupe_key = f"reply:{reply_replay_id}"
                    exists = db.scalar(
                        select(Notification)
                        .where(Notification.user_id == recipient)
                        .where(Notification.dedupe_key == dedupe_key)
                        .limit(1)
                    )
                    if not exists:
                        challenger = db.get(User, str(user_id))
                        challenger_name = (
                            str(challenger.display_name)
                            if challenger and challenger.display_name
                            else "Someone"
                        )
                        db.add(
                            Notification(
                                id=f"nt_{uuid4().hex}",
                                user_id=recipient,
                                type="reply_clip_shared",
                                title="Reply clip shared"[:120],
                                body=f"{challenger_name} shared a reply to your clip"[:200],
                                href=f"/replay/{match_id}?reply_to={parent_replay_id}"
                                if match_id
                                else f"/s/clip/{parent_replay_id}",
                                dedupe_key=dedupe_key,
                                meta_json=orjson.dumps(
                                    {
                                        "parent_replay_id": parent_replay_id,
                                        "reply_replay_id": reply_replay_id,
                                        "match_id": match_id or None,
                                        "challenger_user_id": str(user_id),
                                    }
                                ).decode("utf-8"),
                                created_at=datetime.now(UTC),
                                read_at=None,
                            )
                        )
        except Exception:  # noqa: BLE001
            pass
    try:
        from neuroleague_api.quests_engine import apply_event_to_quests

        apply_event_to_quests(db, event=ev)
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return TrackEventResponse(ok=True)
