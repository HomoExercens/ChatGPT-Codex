from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
import math
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import (
    device_id_from_request,
    ip_hash_from_request,
    log_event,
    user_agent_hash_from_request,
)
from neuroleague_api.experiments import assign_experiment
from neuroleague_api.models import (
    Blueprint,
    Challenge,
    ChallengeAttempt,
    ClipLike,
    Event,
    FeaturedItem,
    Match,
    ModerationHide,
    ReplayReaction,
    Replay,
    RenderJob,
    User,
    UserHiddenClip,
)
from neuroleague_api.rate_limit import check_rate_limit_dual
from neuroleague_api.storage import load_replay_json
from neuroleague_api.storage_backend import get_storage_backend

router = APIRouter(prefix="/api/clips", tags=["clips"])


class ClipAuthorOut(BaseModel):
    user_id: str
    display_name: str


class ClipStatsOut(BaseModel):
    likes: int
    forks: int
    views: int
    shares: int
    open_ranked: int


class ClipFeedItemOut(BaseModel):
    clip_id: str
    replay_id: str
    match_id: str
    author: ClipAuthorOut
    blueprint_id: str | None
    blueprint_name: str | None
    mode: Literal["1v1", "team"]
    ruleset_version: str
    created_at: datetime
    best_clip_status: Literal["ready", "rendering", "missing"]
    vertical_mp4_url: str | None
    share_url_vertical: str
    thumb_url: str
    stats: ClipStatsOut
    tags: list[str] = Field(default_factory=list)
    featured: bool = False
    hero: bool = False


class ClipFeedOut(BaseModel):
    items: list[ClipFeedItemOut]
    next_cursor: str | None = None


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _encode_cursor(*, created_at: datetime, match_id: str) -> str:
    created_at = _as_aware(created_at) or datetime.fromtimestamp(0, tz=UTC)
    payload = {"t": created_at.isoformat(), "id": match_id}
    raw = orjson.dumps(payload)
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    raw = str(cursor or "").strip()
    if not raw:
        raise ValueError("empty cursor")
    pad = "=" * (-len(raw) % 4)
    data = base64.urlsafe_b64decode(raw + pad)
    obj = orjson.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("invalid cursor")
    t = obj.get("t")
    mid = obj.get("id")
    if not isinstance(t, str) or not isinstance(mid, str):
        raise ValueError("invalid cursor")
    dt = datetime.fromisoformat(t)
    dt = _as_aware(dt) or datetime.fromtimestamp(0, tz=UTC)
    return dt, mid


def _decay(
    *, now: datetime, created_at: datetime, half_life_hours: float = 48.0
) -> float:
    created_at = _as_aware(created_at) or now
    age_h = max(0.0, (now - created_at).total_seconds() / 3600.0)
    try:
        return math.exp(-age_h / float(half_life_hours))
    except Exception:  # noqa: BLE001
        return 0.0


def _reaction_actor_id(
    *, user_id: str | None, request: Request
) -> tuple[str, str | None]:
    uid = str(user_id or "")
    is_guest = uid.startswith("guest_")
    if uid and not is_guest:
        return f"u:{uid}", uid

    dev = device_id_from_request(request)
    if dev:
        return f"d:{dev}", None

    ip_hash = ip_hash_from_request(request)
    ua_hash = user_agent_hash_from_request(request)
    if ip_hash and ua_hash:
        return f"a:{ip_hash[:24]}:{ua_hash[:24]}", None
    if ip_hash:
        return f"ip:{ip_hash[:32]}", None

    # Fallback: keep per-user behavior even if it's a guest.
    return f"u:{uid or 'anon'}", uid or None


class ReactionCountsOut(BaseModel):
    up: int = 0
    lol: int = 0
    wow: int = 0
    total: int = 0


class ReactRequest(BaseModel):
    reaction_type: Literal["up", "lol", "wow"]
    source: str | None = Field(default=None, max_length=64)


class ReactResponse(BaseModel):
    ok: bool = True
    replay_id: str
    reaction_type: str
    counts: ReactionCountsOut


@dataclass(frozen=True)
class _ClipSegment:
    start_sec: float
    end_sec: float
    start_tick: int
    end_tick: int
    tags: list[str]
    captions_version: str | None = None
    captions_template_id: str | None = None


def _best_segment_from_replay(payload: dict[str, Any]) -> _ClipSegment:
    from neuroleague_api.clip_render import best_clip_segment, captions_plan_for_segment

    highlights = payload.get("highlights")
    top: dict[str, Any] = {}
    if isinstance(highlights, list) and highlights:
        for h in highlights:
            if isinstance(h, dict):
                top = h
                break
    start_tick, end_tick = best_clip_segment(payload, max_duration_sec=12.0)
    start_sec = float(start_tick) / 20.0
    end_sec = float(end_tick) / 20.0
    tags = top.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags_out = [str(t) for t in tags if isinstance(t, (str, int, float))]
    captions_plan = captions_plan_for_segment(
        replay_payload=payload, start_tick=start_tick, end_tick=end_tick
    )
    return _ClipSegment(
        start_sec=start_sec,
        end_sec=end_sec,
        start_tick=start_tick,
        end_tick=end_tick,
        tags=tags_out[:12],
        captions_version=captions_plan.version,
        captions_template_id=captions_plan.template_id,
    )


def _best_clip_status(
    *,
    db: Session,
    backend,
    replay_id: str,
    digest: str,
    seg: _ClipSegment,
) -> tuple[Literal["ready", "rendering", "missing"], str | None]:
    if not digest:
        return "missing", None
    from neuroleague_api.clip_render import CAPTIONS_VERSION, cache_key

    mp4_key = cache_key(
        replay_digest=digest,
        kind="clip_mp4",
        start_tick=seg.start_tick,
        end_tick=seg.end_tick,
        fps=12,
        scale=1,
        theme="dark",
        aspect="9:16",
        captions_version=str(seg.captions_version or CAPTIONS_VERSION),
        captions_template_id=seg.captions_template_id,
    )
    asset_key = f"clips/mp4/clip_mp4_{replay_id}_{mp4_key[:16]}.mp4"
    try:
        if backend.exists(key=asset_key):
            return "ready", backend.public_url(key=asset_key)
    except Exception:  # noqa: BLE001
        pass

    existing = db.scalar(
        select(RenderJob)
        .where(RenderJob.cache_key == mp4_key)
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )
    if existing and existing.status in ("queued", "running"):
        return "rendering", None
    return "missing", None


@router.get("/feed", response_model=ClipFeedOut)
def feed(
    mode: Literal["1v1", "team"] = "1v1",
    sort: Literal["trending", "new"] = "trending",
    algo: Literal["v1", "v2", "v3"] = "v2",
    hero: bool = Query(default=False),
    limit: int = Query(default=12, ge=1, le=30),
    cursor: str | None = None,
    _viewer_user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ClipFeedOut:
    settings = Settings()
    ruleset = settings.ruleset_version
    now = datetime.now(UTC)

    hidden_replay_ids = db.scalars(
        select(UserHiddenClip.replay_id).where(
            UserHiddenClip.user_id == _viewer_user_id
        )
    ).all()
    global_hidden_replay_ids = db.scalars(
        select(ModerationHide.target_id).where(ModerationHide.target_type == "clip")
    ).all()

    cursor_t: datetime | None = None
    cursor_id: str | None = None
    if cursor:
        try:
            cursor_t, cursor_id = _decode_cursor(cursor)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid cursor") from None

    def _load_hero_ids() -> list[str]:
        try:
            from neuroleague_api.hero_clips import load_hero_replay_ids

            return load_hero_replay_ids(mode=mode)
        except Exception:  # noqa: BLE001
            return []

    pinned_pairs: list[tuple[Match, Replay, bool]] = []
    pinned_ids: list[str] = []
    pinned_take = min(5 if hero else 3, max(0, int(limit) - 1))
    if cursor is None and pinned_take > 0:
        hero_ids: list[str] = []
        if hero:
            for rid in _load_hero_ids():
                if not rid:
                    continue
                if rid in hidden_replay_ids:
                    continue
                if rid in global_hidden_replay_ids:
                    continue
                if rid not in hero_ids:
                    hero_ids.append(rid)
                if len(hero_ids) >= pinned_take:
                    break

        pinned_ids = list(hero_ids)
        fill = max(0, pinned_take - len(pinned_ids))
        if fill > 0:
            fq = (
                select(FeaturedItem)
                .where(FeaturedItem.kind == "clip")
                .where(FeaturedItem.status == "active")
                .where((FeaturedItem.starts_at.is_(None)) | (FeaturedItem.starts_at <= now))
                .where((FeaturedItem.ends_at.is_(None)) | (FeaturedItem.ends_at > now))
                .order_by(desc(FeaturedItem.priority), desc(FeaturedItem.created_at))
                .limit(int(fill) * 3)
            )
            featured = db.scalars(fq).all()
            for fi in featured:
                rid = str(fi.target_id or "").strip()
                if not rid:
                    continue
                if rid in hero_ids:
                    continue
                if rid in hidden_replay_ids:
                    continue
                if rid in global_hidden_replay_ids:
                    continue
                if rid not in pinned_ids:
                    pinned_ids.append(rid)
                if len(pinned_ids) >= pinned_take:
                    break

        if pinned_ids:
            pinned_rows = db.execute(
                select(Match, Replay)
                .join(Replay, Replay.match_id == Match.id)
                .where(Replay.id.in_(pinned_ids))
                .where(Match.status == "done")
                .where(Match.mode == mode)
                .where(Match.ruleset_version == ruleset)
            ).all()
            by_rid = {str(r.id): (m, r) for (m, r) in pinned_rows if r and m}
            for rid in pinned_ids:
                pair = by_rid.get(str(rid))
                if pair:
                    is_hero = bool(hero and (rid in hero_ids or not hero_ids))
                    pinned_pairs.append((pair[0], pair[1], is_hero))

    base_q = (
        select(Match, Replay)
        .join(Replay, Replay.match_id == Match.id)
        .where(Match.status == "done")
        .where(Match.mode == mode)
        .where(Match.ruleset_version == ruleset)
    )
    if pinned_ids:
        base_q = base_q.where(~Replay.id.in_(pinned_ids))
    if hidden_replay_ids:
        base_q = base_q.where(~Replay.id.in_(hidden_replay_ids))
    if global_hidden_replay_ids:
        base_q = base_q.where(~Replay.id.in_(global_hidden_replay_ids))

    if sort == "trending":
        base_q = base_q.where(Match.created_at >= now - timedelta(days=7))

    base_q = base_q.order_by(desc(Match.created_at), desc(Match.id))
    if cursor_t is not None and cursor_id is not None:
        base_q = base_q.where(
            (Match.created_at < cursor_t)
            | ((Match.created_at == cursor_t) & (Match.id < cursor_id))
        )

    # Oversample candidates for trending scoring.
    oversample = int(limit) * (6 if sort == "trending" else 2)
    rows = db.execute(base_q.limit(max(50, oversample))).all()
    if not rows:
        return ClipFeedOut(items=[], next_cursor=None)

    match_by_id: dict[str, Match] = {}
    replay_by_match: dict[str, Replay] = {}
    for m, r in rows:
        match_by_id[str(m.id)] = m
        replay_by_match[str(m.id)] = r

    # Resolve authors and blueprints.
    all_matches = list(match_by_id.values()) + [m for (m, _r, _hero_flag) in pinned_pairs]
    user_ids = sorted({str(m.user_a_id) for m in all_matches if m.user_a_id})
    bp_ids = sorted({str(m.blueprint_a_id) for m in all_matches if m.blueprint_a_id})
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    bps = (
        db.scalars(select(Blueprint).where(Blueprint.id.in_(bp_ids))).all()
        if bp_ids
        else []
    )
    user_by_id = {u.id: u for u in users}
    bp_by_id = {b.id: b for b in bps}

    # Likes: current count per replay (not time-windowed; toggled state is stored).
    replay_ids = [str(replay_by_match[mid].id) for mid in match_by_id.keys()]
    for _m, r, _hero_flag in pinned_pairs:
        rid = str(r.id)
        if rid not in replay_ids:
            replay_ids.append(rid)
    like_rows = (
        db.execute(
            select(ClipLike.replay_id, func.count(ClipLike.user_id))
            .where(ClipLike.replay_id.in_(replay_ids))
            .group_by(ClipLike.replay_id)
        ).all()
        if replay_ids
        else []
    )
    likes_by_replay = {str(rid): int(cnt or 0) for rid, cnt in like_rows}

    # Events: last 7 days (with per-user/day dedupe).
    algo_norm = str(algo).lower()
    algo_norm = algo_norm if algo_norm in {"v1", "v2", "v3"} else "v2"
    if algo_norm == "v1":
        event_types = {
            "clip_view": 1.0,
            "clip_share": 5.0,
            "clip_fork_click": 6.0,
            "fork_click": 6.0,
            "fork_created": 9.0,
            "clip_open_ranked": 4.0,
        }
        like_weight = 3.0
    elif algo_norm == "v2":
        # Viral v2: bias toward conversion-ish actions over raw views.
        event_types = {
            "clip_view": 0.25,
            "clip_completion": 2.0,
            "clip_share": 5.0,
            "clip_fork_click": 7.0,
            "fork_click": 7.0,
            "fork_created": 12.0,
            "clip_open_ranked": 9.0,
        }
        like_weight = 2.0
    else:
        # Viral v3: emphasize completion and "open ranked" (meant for A/B tests).
        event_types = {
            "clip_view": 0.2,
            "clip_completion": 3.0,
            "clip_share": 5.0,
            "clip_fork_click": 8.0,
            "fork_click": 8.0,
            "fork_created": 14.0,
            "clip_open_ranked": 12.0,
        }
        like_weight = 1.75
    since = now - timedelta(days=7)
    events = db.scalars(
        select(Event)
        .where(Event.created_at >= since)
        .where(Event.type.in_(list(event_types.keys())))
        .order_by(desc(Event.created_at))
        .limit(50_000)
    ).all()

    def _payload(ev: Event) -> dict[str, Any]:
        try:
            obj = orjson.loads(ev.payload_json or "{}")
        except Exception:  # noqa: BLE001
            return {}
        return obj if isinstance(obj, dict) else {}

    def _extract_replay_id(p: dict[str, Any]) -> str:
        rid = p.get("replay_id") or p.get("source_replay_id")
        if rid:
            return str(rid)
        meta = p.get("meta")
        if isinstance(meta, dict):
            rid2 = meta.get("replay_id") or meta.get("source_replay_id")
            if rid2:
                return str(rid2)
        return ""

    # Aggregate stats + trending score.
    stats: dict[str, dict[str, float]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    for ev in events:
        p = _payload(ev)
        rid = _extract_replay_id(p)
        if not rid or rid not in likes_by_replay and rid not in replay_ids:
            continue
        uid = str(ev.user_id or "anon")
        day = (_as_aware(ev.created_at) or now).strftime("%Y%m%d")
        dedupe_type = str(ev.type)
        if dedupe_type in {"clip_fork_click", "fork_click", "fork_created"}:
            dedupe_type = "fork"
        key = (rid, dedupe_type, uid, day)
        if key in seen:
            continue
        seen.add(key)

        w = float(event_types.get(str(ev.type), 0.0))
        d = _decay(now=now, created_at=_as_aware(ev.created_at) or now)
        row = stats.setdefault(
            rid,
            {
                "views": 0.0,
                "completions": 0.0,
                "shares": 0.0,
                "forks": 0.0,
                "open_ranked": 0.0,
                "score": 0.0,
            },
        )
        if dedupe_type == "fork":
            row["forks"] += 1.0
        elif ev.type == "clip_view":
            row["views"] += 1.0
        elif ev.type == "clip_completion":
            row["completions"] += 1.0
        elif ev.type == "clip_share":
            row["shares"] += 1.0
        elif ev.type == "clip_open_ranked":
            row["open_ranked"] += 1.0
        row["score"] += w * d

    # Add likes into score with decay (based on like created_at).
    like_since_rows = (
        db.scalars(
            select(ClipLike)
            .where(ClipLike.replay_id.in_(replay_ids))
            .where(ClipLike.created_at >= since)
        ).all()
        if replay_ids
        else []
    )
    for lk in like_since_rows:
        rid = str(lk.replay_id)
        d = _decay(now=now, created_at=_as_aware(lk.created_at) or now)
        row = stats.setdefault(
            rid,
            {
                "views": 0.0,
                "completions": 0.0,
                "shares": 0.0,
                "forks": 0.0,
                "open_ranked": 0.0,
                "score": 0.0,
            },
        )
        row["score"] += float(like_weight) * d

    backend = get_storage_backend()

    def build_item(
        *, m: Match, replay: Replay, featured_flag: bool, hero_flag: bool = False
    ) -> ClipFeedItemOut:
        created_at = _as_aware(m.created_at) or now
        u = user_by_id.get(str(m.user_a_id))
        bp = bp_by_id.get(str(m.blueprint_a_id)) if m.blueprint_a_id else None

        payload = load_replay_json(artifact_path=replay.artifact_path)
        seg = _best_segment_from_replay(payload if isinstance(payload, dict) else {})
        digest = str(
            replay.digest
            or (payload.get("digest") if isinstance(payload, dict) else "")
            or ""
        )
        status, mp4_url = _best_clip_status(
            db=db,
            backend=backend,
            replay_id=replay.id,
            digest=digest,
            seg=seg,
        )

        q = f"start={seg.start_sec:.1f}&end={seg.end_sec:.1f}"
        share_url_vertical = f"/s/clip/{replay.id}?{q}&v=1"
        thumb_url = f"/s/clip/{replay.id}/thumb.png?{q}&scale=1&theme=dark"

        st = stats.get(str(replay.id), {})
        return ClipFeedItemOut(
            clip_id=str(replay.id),
            replay_id=str(replay.id),
            match_id=str(m.id),
            author=ClipAuthorOut(
                user_id=str(m.user_a_id),
                display_name=u.display_name if u else "Lab_Unknown",
            ),
            blueprint_id=str(m.blueprint_a_id) if m.blueprint_a_id else None,
            blueprint_name=bp.name if bp else None,
            mode=m.mode,  # type: ignore[arg-type]
            ruleset_version=str(m.ruleset_version),
            created_at=created_at,
            best_clip_status=status,
            vertical_mp4_url=mp4_url if status == "ready" else None,
            share_url_vertical=share_url_vertical,
            thumb_url=thumb_url,
            stats=ClipStatsOut(
                likes=int(likes_by_replay.get(str(replay.id), 0)),
                views=int(st.get("views") or 0),
                shares=int(st.get("shares") or 0),
                forks=int(st.get("forks") or 0),
                open_ranked=int(st.get("open_ranked") or 0),
            ),
            tags=seg.tags,
            featured=bool(featured_flag),
            hero=bool(hero_flag),
        )

    featured_items_out: list[ClipFeedItemOut] = []
    for m, r, is_hero in pinned_pairs:
        try:
            featured_items_out.append(
                build_item(m=m, replay=r, featured_flag=True, hero_flag=is_hero)
            )
        except Exception:  # noqa: BLE001
            continue

    items: list[ClipFeedItemOut] = []
    for mid, m in match_by_id.items():
        replay = replay_by_match.get(mid)
        if not replay:
            continue
        try:
            items.append(build_item(m=m, replay=replay, featured_flag=False))
        except Exception:  # noqa: BLE001
            continue

    if sort == "new":
        items.sort(key=lambda it: (-it.created_at.timestamp(), it.match_id))
    else:
        items.sort(
            key=lambda it: (
                -(float(stats.get(it.replay_id, {}).get("score") or 0.0)),
                -it.created_at.timestamp(),
                it.match_id,
            )
        )

    if cursor is None and featured_items_out:
        take = min(int(pinned_take), len(featured_items_out), int(limit))
        normal_limit = max(0, int(limit) - take)
        normal_out = items[:normal_limit]
        out = featured_items_out[:take] + normal_out
        next_cursor = None
        if normal_out:
            last = normal_out[-1]
            next_cursor = _encode_cursor(
                created_at=last.created_at, match_id=last.match_id
            )
        return ClipFeedOut(items=out, next_cursor=next_cursor)

    out = items[: int(limit)]
    next_cursor = None
    if len(out) >= int(limit):
        last = out[-1]
        next_cursor = _encode_cursor(created_at=last.created_at, match_id=last.match_id)

    return ClipFeedOut(items=out, next_cursor=next_cursor)


class ClipShareUrlOut(BaseModel):
    share_url_vertical: str
    start_sec: float
    end_sec: float
    variant: str
    captions_template_id: str | None = None
    captions_version: str


def _duration_from_clip_len_variant(variant: str) -> float:
    v = str(variant or "").strip()
    if v == "10s":
        return 10.0
    if v == "15s":
        return 15.0
    return 12.0


@router.get("/{replay_id}/share_url", response_model=ClipShareUrlOut)
def share_url(
    request: Request,
    replay_id: str,
    orientation: Literal["vertical"] = "vertical",
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ClipShareUrlOut:
    if orientation != "vertical":
        raise HTTPException(status_code=400, detail="Unsupported orientation")

    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    subject_type = "guest" if str(user_id or "").startswith("guest_") else "user"
    variant, _cfg, is_new = assign_experiment(
        db,
        subject_type=subject_type,
        subject_id=str(user_id),
        experiment_key="clip_len_v1",
    )
    if is_new:
        log_event(
            db,
            type="experiment_exposed",
            user_id=user_id,
            request=request,
            payload={"experiment_key": "clip_len_v1", "variant": variant},
        )
        db.commit()

    max_duration_sec = _duration_from_clip_len_variant(variant)

    payload = load_replay_json(artifact_path=replay.artifact_path)
    if not isinstance(payload, dict):
        payload = {}

    from neuroleague_api.clip_render import (
        CAPTIONS_VERSION,
        best_clip_segment,
        captions_plan_for_segment,
        clamp_clip_params,
    )

    st_raw, et_raw = best_clip_segment(payload, max_duration_sec=max_duration_sec)
    start_sec = float(f"{(float(st_raw) / 20.0):.1f}")
    end_sec = float(f"{(float(et_raw) / 20.0):.1f}")

    # Align to share URL 0.1s resolution so /s/clip hits the same cache key.
    start_tick, end_tick, _fps, _scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=start_sec,
        end_sec=end_sec,
        fps=12,
        scale=1,
        max_duration_sec=max_duration_sec,
    )
    start_sec = float(f"{(float(start_tick) / 20.0):.1f}")
    end_sec = float(f"{(float(end_tick) / 20.0):.1f}")

    cap_variant, _cap_cfg, cap_is_new = assign_experiment(
        db,
        subject_type="replay",
        subject_id=str(replay_id),
        experiment_key="captions_v2",
    )
    if cap_is_new:
        log_event(
            db,
            type="experiment_exposed",
            user_id=user_id,
            request=request,
            payload={
                "experiment_key": "captions_v2",
                "variant": cap_variant,
                "subject_type": "replay",
                "subject_id": replay_id,
            },
        )
        db.commit()
    forced_template_id = str(cap_variant) if str(cap_variant) in {"A", "B", "C"} else None

    captions_plan = captions_plan_for_segment(
        replay_payload=payload,
        replay_id=replay_id,
        start_tick=start_tick,
        end_tick=end_tick,
        template_id=forced_template_id,
    )
    captions_version = str(captions_plan.version or CAPTIONS_VERSION)
    captions_template_id = captions_plan.template_id

    q = urlencode(
        [
            ("start", f"{start_sec:.1f}"),
            ("end", f"{end_sec:.1f}"),
            ("v", "1"),
            ("lenv", str(variant)),
            ("cv", captions_version),
            *(
                [("ctpl", str(captions_template_id))]
                if captions_template_id
                else []
            ),
        ]
    )
    return ClipShareUrlOut(
        share_url_vertical=f"/s/clip/{replay_id}?{q}",
        start_sec=start_sec,
        end_sec=end_sec,
        variant=str(variant),
        captions_template_id=captions_template_id,
        captions_version=captions_version,
    )


class ClipEventRequest(BaseModel):
    type: Literal["view", "like", "share", "fork_click", "open_ranked", "completion"]
    source: str | None = Field(default=None, max_length=32)
    meta: dict[str, Any] = Field(default_factory=dict)


class ClipEventResponse(BaseModel):
    ok: bool = True
    type: str
    replay_id: str
    liked: bool | None = None
    likes: int | None = None


@router.post("/{replay_id}/event", response_model=ClipEventResponse)
def track_event(
    request: Request,
    replay_id: str,
    req: ClipEventRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ClipEventResponse:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="clip_events",
        per_minute_user=int(settings.rate_limit_clip_events_per_minute),
        per_hour_user=int(settings.rate_limit_clip_events_per_hour),
        per_minute_ip=int(settings.rate_limit_clip_events_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_clip_events_per_hour_ip),
        extra_detail={"type": req.type},
    )

    now = datetime.now(UTC)
    event_type = f"clip_{req.type}"

    if req.type == "like":
        existing = db.get(ClipLike, {"user_id": user_id, "replay_id": replay_id})
        liked = False
        if existing:
            db.delete(existing)
            liked = False
        else:
            db.add(ClipLike(user_id=user_id, replay_id=replay_id, created_at=now))
            liked = True
        db.commit()

        likes = int(
            db.scalar(
                select(func.count(ClipLike.user_id)).where(
                    ClipLike.replay_id == replay_id
                )
            )
            or 0
        )

        db.add(
            Event(
                id=f"ev_{uuid4().hex}",
                user_id=user_id,
                type="clip_like_toggle",
                payload_json=orjson.dumps(
                    {
                        "replay_id": replay_id,
                        "match_id": replay.match_id,
                        "liked": liked,
                        "source": req.source,
                        "meta": req.meta,
                    }
                ).decode("utf-8"),
                created_at=now,
            )
        )
        db.commit()

        return ClipEventResponse(
            ok=True, type=req.type, replay_id=replay_id, liked=liked, likes=likes
        )

    # Non-like events are append-only and aggregated for trending.
    ev = Event(
        id=f"ev_{uuid4().hex}",
        user_id=user_id,
        type=event_type,
        payload_json=orjson.dumps(
            {
                "replay_id": replay_id,
                "match_id": replay.match_id,
                "source": req.source,
                "meta": req.meta,
            }
        ).decode("utf-8"),
        created_at=now,
    )
    db.add(ev)
    try:
        from neuroleague_api.quests_engine import apply_event_to_quests

        apply_event_to_quests(db, event=ev)
    except Exception:  # noqa: BLE001
        pass

    if req.type == "share":
        ev2 = Event(
            id=f"ev_{uuid4().hex}",
            user_id=user_id,
            type="share_action",
            payload_json=orjson.dumps(
                {
                    "replay_id": replay_id,
                    "match_id": replay.match_id,
                    "source": req.source,
                    "meta": req.meta,
                }
            ).decode("utf-8"),
            created_at=now,
        )
        db.add(ev2)
        try:
            from neuroleague_api.quests_engine import apply_event_to_quests

            apply_event_to_quests(db, event=ev2)
        except Exception:  # noqa: BLE001
            pass
    db.commit()
    return ClipEventResponse(ok=True, type=req.type, replay_id=replay_id)


@router.post("/{replay_id}/react", response_model=ReactResponse)
def react(
    request: Request,
    replay_id: str,
    req: ReactRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ReactResponse:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="clip_reactions",
        per_minute_user=int(settings.rate_limit_clip_events_per_minute),
        per_hour_user=int(settings.rate_limit_clip_events_per_hour),
        per_minute_ip=int(settings.rate_limit_clip_events_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_clip_events_per_hour_ip),
        extra_detail={"reaction_type": str(req.reaction_type)},
    )

    now = datetime.now(UTC)
    actor_id, stored_user_id = _reaction_actor_id(user_id=user_id, request=request)

    row = ReplayReaction(
        id=f"rr_{uuid4().hex}",
        replay_id=str(replay_id),
        actor_id=str(actor_id)[:96],
        user_id=str(stored_user_id)[:64] if stored_user_id else None,
        reaction_type=str(req.reaction_type)[:16],
        created_at=now,
    )
    db.add(row)
    inserted = False
    try:
        db.commit()
        inserted = True
    except IntegrityError:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        inserted = False

    # Append analytics event (best-effort, even if deduped).
    try:
        ev = log_event(
            db,
            type="reaction_click",
            user_id=user_id,
            request=request,
            payload={
                "reaction_type": str(req.reaction_type),
                "target_replay_id": str(replay_id),
                "source": str(req.source or "unknown")[:64] if req.source else None,
                "logged_in": False if str(user_id or "").startswith("guest_") else True,
                "deduped": False if inserted else True,
            },
            now=now,
        )
        try:
            from neuroleague_api.quests_engine import apply_event_to_quests

            apply_event_to_quests(db, event=ev)
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    except Exception:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass

    rows = db.execute(
        select(ReplayReaction.reaction_type, func.count(ReplayReaction.id))
        .where(ReplayReaction.replay_id == replay_id)
        .group_by(ReplayReaction.reaction_type)
    ).all()
    counts: dict[str, int] = {str(t): int(c or 0) for t, c in rows if t}
    out_counts = ReactionCountsOut(
        up=int(counts.get("up", 0)),
        lol=int(counts.get("lol", 0)),
        wow=int(counts.get("wow", 0)),
        total=int(sum(counts.values())),
    )
    return ReactResponse(
        ok=True,
        replay_id=str(replay_id),
        reaction_type=str(req.reaction_type),
        counts=out_counts,
    )


@router.get("/{replay_id}/reactions", response_model=ReactionCountsOut)
def reaction_counts(
    replay_id: str,
    db: Session = DBSession,
) -> ReactionCountsOut:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    rows = db.execute(
        select(ReplayReaction.reaction_type, func.count(ReplayReaction.id))
        .where(ReplayReaction.replay_id == replay_id)
        .group_by(ReplayReaction.reaction_type)
    ).all()
    counts: dict[str, int] = {str(t): int(c or 0) for t, c in rows if t}
    return ReactionCountsOut(
        up=int(counts.get("up", 0)),
        lol=int(counts.get("lol", 0)),
        wow=int(counts.get("wow", 0)),
        total=int(sum(counts.values())),
    )


class ReplyLineageOut(BaseModel):
    fork_depth: int = 0
    forked_from_id: str | None = None
    forked_from_name: str | None = None
    fork_root_id: str | None = None
    fork_root_name: str | None = None


class ReplyClipOut(BaseModel):
    reply_replay_id: str
    match_id: str
    outcome: Literal["win", "loss", "draw"]
    created_at: datetime | None = None
    finished_at: datetime | None = None
    challenger_user_id: str
    challenger_display_name: str | None = None
    blueprint_id: str | None = None
    blueprint_name: str | None = None
    likes: int = 0
    completions: int = 0
    shares: int = 0
    reactions: ReactionCountsOut = Field(default_factory=ReactionCountsOut)
    lineage: ReplyLineageOut = Field(default_factory=ReplyLineageOut)


class RepliesResponse(BaseModel):
    sort: Literal["top", "recent"]
    algo_variant: str
    items: list[ReplyClipOut]


def _reply_outcome(result: str | None) -> Literal["win", "loss", "draw"]:
    r = str(result or "")
    if r == "A":
        return "win"
    if r == "B":
        return "loss"
    return "draw"


def _reply_score_variant_a(*, now: datetime, item: dict[str, Any]) -> tuple[int, float]:
    outcome = str(item.get("outcome") or "")
    win_rank = 2 if outcome == "win" else 1 if outcome == "draw" else 0
    ts = item.get("finished_at") or item.get("created_at") or now
    ts = _as_aware(ts) or now
    decay = _decay(now=now, created_at=ts, half_life_hours=48.0)

    likes = float(item.get("likes") or 0)
    shares = float(item.get("shares") or 0)
    completions = float(item.get("completions") or 0)
    rx = item.get("reactions") or {}
    reactions_total = float(
        (rx.get("up") or 0) + (rx.get("lol") or 0) + (rx.get("wow") or 0)
    )

    engagement = (3.0 * reactions_total) + (2.0 * shares) + (1.0 * completions) + (0.2 * likes)
    base = (decay * 10_000.0) + (decay * 100.0 * engagement)
    return win_rank, base


@router.get("/{replay_id}/replies", response_model=RepliesResponse)
def list_replies(
    request: Request,
    replay_id: str,
    sort: Literal["top", "recent"] = "top",
    limit: int = 12,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> RepliesResponse:
    limit = max(1, min(30, int(limit)))
    now = datetime.now(UTC)

    algo_variant = "control"
    try:
        subject_type = "guest" if str(user_id or "").startswith("guest_") else "user"
        algo_variant, _cfg, _is_new = assign_experiment(
            db,
            subject_type=subject_type,
            subject_id=str(user_id),
            experiment_key="replies_rank_algo_v1",
        )
        algo_variant = str(algo_variant or "control")
    except Exception:  # noqa: BLE001
        algo_variant = "control"

    # Fetch a wider candidate set; we will re-rank in Python for "top".
    candidate_limit = limit if sort == "recent" else max(limit * 6, 60)

    likes_subq = (
        select(
            ClipLike.replay_id.label("replay_id"),
            func.count(ClipLike.user_id).label("likes"),
        )
        .group_by(ClipLike.replay_id)
        .subquery()
    )

    rows = db.execute(
        select(
            Match.id.label("match_id"),
            Match.result,
            Match.finished_at,
            Match.created_at,
            Match.blueprint_a_id,
            Match.blueprint_b_id,
            ChallengeAttempt.challenger_user_id,
            Replay.id.label("reply_replay_id"),
            func.coalesce(likes_subq.c.likes, 0).label("likes"),
        )
        .join(Challenge, Challenge.id == ChallengeAttempt.challenge_id)
        .join(Match, Match.id == ChallengeAttempt.match_id)
        .join(Replay, Replay.match_id == Match.id)
        .outerjoin(likes_subq, likes_subq.c.replay_id == Replay.id)
        .where(Challenge.kind == "clip")
        .where(Challenge.target_replay_id == replay_id)
        .where(Match.status == "done")
        .order_by(
            desc(case((Match.result == "A", 1), else_=0)),
            desc(func.coalesce(Match.finished_at, Match.created_at)),
            desc(func.coalesce(likes_subq.c.likes, 0)),
            desc(Match.created_at),
        )
        .limit(int(candidate_limit))
    ).all()

    if not rows:
        return RepliesResponse(sort=sort, algo_variant=algo_variant, items=[])

    reply_ids = [str(r.reply_replay_id) for r in rows if getattr(r, "reply_replay_id", None)]
    challenger_ids = sorted({str(r.challenger_user_id) for r in rows if r.challenger_user_id})
    bp_ids = sorted({str(r.blueprint_a_id) for r in rows if r.blueprint_a_id})

    users = (
        db.scalars(select(User).where(User.id.in_(challenger_ids))).all()
        if challenger_ids
        else []
    )
    user_by_id = {u.id: u for u in users}

    bps = (
        db.scalars(select(Blueprint).where(Blueprint.id.in_(bp_ids))).all()
        if bp_ids
        else []
    )
    bp_by_id = {b.id: b for b in bps}

    # Parents/roots for lineage summary.
    extra_bp_ids: set[str] = set()
    for b in bps:
        if b.forked_from_id:
            extra_bp_ids.add(str(b.forked_from_id))
        if b.fork_root_blueprint_id:
            extra_bp_ids.add(str(b.fork_root_blueprint_id))
    extra_bp_ids.difference_update(bp_by_id.keys())
    if extra_bp_ids:
        extras = db.scalars(
            select(Blueprint).where(Blueprint.id.in_(sorted(extra_bp_ids)))
        ).all()
        for b in extras:
            bp_by_id[b.id] = b

    # Reaction counts.
    rx_rows = (
        db.execute(
            select(
                ReplayReaction.replay_id,
                ReplayReaction.reaction_type,
                func.count(ReplayReaction.id),
            )
            .where(ReplayReaction.replay_id.in_(reply_ids))
            .group_by(ReplayReaction.replay_id, ReplayReaction.reaction_type)
        ).all()
        if reply_ids
        else []
    )
    rx_by_replay: dict[str, dict[str, int]] = {}
    for rid, rtype, cnt in rx_rows:
        rkey = str(rid or "")
        tkey = str(rtype or "")
        if not rkey or not tkey:
            continue
        rx_by_replay.setdefault(rkey, {})[tkey] = int(cnt or 0)

    # Engagement stats for ranking (best-effort).
    since = now - timedelta(days=14)
    engagement_events = db.scalars(
        select(Event)
        .where(Event.created_at >= since)
        .where(Event.type.in_(["clip_completion", "clip_share", "reply_clip_shared"]))
        .order_by(Event.created_at.asc())
    ).all()
    completions: dict[str, int] = {}
    shares: dict[str, int] = {}
    for ev in engagement_events:
        try:
            payload = orjson.loads(ev.payload_json or "{}")
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        if str(ev.type) == "reply_clip_shared":
            rid = str(payload.get("reply_replay_id") or "")
            if rid and rid in reply_ids:
                shares[rid] = int(shares.get(rid, 0) + 1)
            continue
        rid = str(payload.get("replay_id") or "")
        if not rid or rid not in reply_ids:
            continue
        if str(ev.type) == "clip_completion":
            completions[rid] = int(completions.get(rid, 0) + 1)
        elif str(ev.type) == "clip_share":
            shares[rid] = int(shares.get(rid, 0) + 1)

    items_raw: list[dict[str, Any]] = []
    for r in rows:
        reply_rid = str(r.reply_replay_id or "")
        if not reply_rid:
            continue
        u = user_by_id.get(str(r.challenger_user_id))
        bp = bp_by_id.get(str(r.blueprint_a_id or "")) if r.blueprint_a_id else None
        parent_bp = (
            bp_by_id.get(str(bp.forked_from_id)) if (bp and bp.forked_from_id) else None
        )
        root_bp = (
            bp_by_id.get(str(bp.fork_root_blueprint_id))
            if (bp and bp.fork_root_blueprint_id)
            else None
        )
        rx = rx_by_replay.get(reply_rid, {})
        items_raw.append(
            {
                "reply_replay_id": reply_rid,
                "match_id": str(r.match_id or ""),
                "outcome": _reply_outcome(r.result),
                "created_at": _as_aware(r.created_at),
                "finished_at": _as_aware(r.finished_at),
                "challenger_user_id": str(r.challenger_user_id or ""),
                "challenger_display_name": (u.display_name if u else None),
                "blueprint_id": str(bp.id) if bp else None,
                "blueprint_name": (bp.name if bp else None),
                "likes": int(r.likes or 0),
                "completions": int(completions.get(reply_rid, 0)),
                "shares": int(shares.get(reply_rid, 0)),
                "reactions": {
                    "up": int(rx.get("up", 0)),
                    "lol": int(rx.get("lol", 0)),
                    "wow": int(rx.get("wow", 0)),
                },
                "lineage": {
                    "fork_depth": int(getattr(bp, "fork_depth", 0) or 0) if bp else 0,
                    "forked_from_id": str(bp.forked_from_id) if (bp and bp.forked_from_id) else None,
                    "forked_from_name": (parent_bp.name if parent_bp else None),
                    "fork_root_id": str(bp.fork_root_blueprint_id)
                    if (bp and bp.fork_root_blueprint_id)
                    else None,
                    "fork_root_name": (root_bp.name if root_bp else None),
                },
                "attacker_bp": str(r.blueprint_a_id or "") or None,
                "defender_bp": str(r.blueprint_b_id or "") or None,
            }
        )

    if sort == "recent":
        items_raw.sort(
            key=lambda it: (
                -float(
                    (_as_aware(it.get("finished_at")) or _as_aware(it.get("created_at")) or now).timestamp()
                ),
                str(it.get("reply_replay_id") or ""),
            )
        )
    else:
        if algo_variant == "variant_a":
            scored: list[tuple[float, dict[str, Any]]] = []
            for it in items_raw:
                win_rank, base = _reply_score_variant_a(now=now, item=it)
                it["_win_rank"] = win_rank
                it["_base_score"] = float(base)
                scored.append((float(win_rank) * 1_000_000.0 + float(base), it))

            scored.sort(
                key=lambda pair: (-pair[0], str(pair[1].get("reply_replay_id") or ""))
            )
            seen_combo: dict[str, int] = {}
            reranked: list[tuple[float, dict[str, Any]]] = []
            for _score, it in scored:
                a = str(it.get("attacker_bp") or "")
                b = str(it.get("defender_bp") or "")
                combo = f"{a}:{b}" if (a or b) else ""
                idx = int(seen_combo.get(combo, 0))
                seen_combo[combo] = idx + 1
                multiplier = 1.0 if idx <= 0 else (0.5**idx)
                final = float(it.get("_win_rank") or 0) * 1_000_000.0 + float(
                    it.get("_base_score") or 0.0
                ) * multiplier
                reranked.append((final, it))

            reranked.sort(
                key=lambda pair: (-pair[0], str(pair[1].get("reply_replay_id") or ""))
            )
            items_raw = [it for _s, it in reranked]

    items_raw = items_raw[:limit]

    out_items: list[ReplyClipOut] = []
    for it in items_raw:
        rx = it.get("reactions") or {}
        out_items.append(
            ReplyClipOut(
                reply_replay_id=str(it.get("reply_replay_id") or ""),
                match_id=str(it.get("match_id") or ""),
                outcome=str(it.get("outcome") or "draw"),  # type: ignore[arg-type]
                created_at=it.get("created_at"),
                finished_at=it.get("finished_at"),
                challenger_user_id=str(it.get("challenger_user_id") or ""),
                challenger_display_name=it.get("challenger_display_name"),
                blueprint_id=it.get("blueprint_id"),
                blueprint_name=it.get("blueprint_name"),
                likes=int(it.get("likes") or 0),
                completions=int(it.get("completions") or 0),
                shares=int(it.get("shares") or 0),
                reactions=ReactionCountsOut(
                    up=int(rx.get("up") or 0),
                    lol=int(rx.get("lol") or 0),
                    wow=int(rx.get("wow") or 0),
                    total=int(
                        (rx.get("up") or 0) + (rx.get("lol") or 0) + (rx.get("wow") or 0)
                    ),
                ),
                lineage=ReplyLineageOut(**(it.get("lineage") or {})),
            )
        )

    return RepliesResponse(sort=sort, algo_variant=algo_variant, items=out_items)


class HideClipResponse(BaseModel):
    ok: bool = True
    replay_id: str
    hidden: bool


@router.post("/{replay_id}/hide", response_model=HideClipResponse)
def hide_clip(
    replay_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> HideClipResponse:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    existing = db.get(UserHiddenClip, {"user_id": user_id, "replay_id": replay_id})
    now = datetime.now(UTC)
    hidden = True
    if existing:
        db.delete(existing)
        hidden = False
    else:
        db.add(UserHiddenClip(user_id=user_id, replay_id=replay_id, created_at=now))
        hidden = True

    db.commit()
    return HideClipResponse(replay_id=replay_id, hidden=hidden)
