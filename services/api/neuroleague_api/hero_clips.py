from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from typing import Any, Literal

import orjson
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import (
    Event,
    Match,
    ModerationHide,
    Replay,
    ReplayReaction,
    Report,
    UserSoftBan,
)
from neuroleague_api.storage import load_replay_json
from neuroleague_api.storage_backend import StorageBackend, get_storage_backend, guess_content_type


HeroMode = Literal["1v1", "team"]


@dataclass(frozen=True)
class HeroCurationConfig:
    window_days: int = 14
    max_items: int = 5
    max_per_user: int = 2
    min_views: int = 10
    min_completions: int = 2
    min_completion_rate: float = 0.20
    half_life_days: float = 5.0
    weights: dict[str, float] | None = None


DEFAULT_WOW_WEIGHTS: dict[str, float] = {
    # Engagement.
    "views": 0.20,
    "completions": 0.90,
    "completion_rate": 2.50,
    "share_open": 1.00,
    "clip_share": 0.90,
    "beat_this_click": 1.20,
    "reply_clip_shared": 1.60,
    "reactions": 0.80,
    # Replay features.
    "highlight_count": 0.35,
    "damage_spikes": 0.65,
    "badge_perfect": 1.25,
    "badge_one_shot": 1.10,
    "badge_clutch": 0.90,
}


def _safe_json(raw: bytes) -> Any:
    try:
        return orjson.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _load_ops_json(backend: StorageBackend, key: str) -> Any:
    try:
        if not backend.exists(key=key):
            return None
        return _safe_json(backend.get_bytes(key=key))
    except Exception:  # noqa: BLE001
        return None


def _dump_ops_json(obj: Any) -> bytes:
    return orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)


def load_hero_override(
    backend: StorageBackend | None = None,
) -> dict[str, Any]:
    backend = backend or get_storage_backend()
    data = _load_ops_json(backend, "ops/hero_clips.override.json")
    return data if isinstance(data, dict) else {}


def ensure_hero_override_exists(
    *,
    backend: StorageBackend | None = None,
    now: datetime | None = None,
) -> None:
    backend = backend or get_storage_backend()
    if backend.exists(key="ops/hero_clips.override.json"):
        return
    now_dt = now or datetime.now(UTC)
    default = {
        "version": 1,
        "updated_at": now_dt.isoformat(),
        "by_mode": {
            "1v1": {"pin": [], "exclude": []},
            "team": {"pin": [], "exclude": []},
        },
        "config": {
            "window_days": 14,
            "max_items": 5,
            "max_per_user": 2,
            "min_views": 10,
            "min_completions": 2,
            "min_completion_rate": 0.20,
            "half_life_days": 5.0,
            "weights": DEFAULT_WOW_WEIGHTS,
        },
    }
    backend.put_bytes(
        key="ops/hero_clips.override.json",
        data=_dump_ops_json(default),
        content_type=guess_content_type("hero_clips.override.json"),
    )


def _ids_from_any_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if not s:
            continue
        if s not in out:
            out.append(s)
    return out


def _ids_from_auto(data: Any, *, mode: HeroMode) -> list[str]:
    if isinstance(data, list):
        return _ids_from_any_list(data)
    if not isinstance(data, dict):
        return []
    by_mode = data.get("by_mode")
    if isinstance(by_mode, dict):
        cur = by_mode.get(str(mode))
        if isinstance(cur, list):
            # Simple list of replay ids.
            return _ids_from_any_list(cur)
        if isinstance(cur, dict):
            items = cur.get("items")
            if isinstance(items, list):
                out: list[str] = []
                for it in items:
                    if isinstance(it, str):
                        rid = it.strip()
                    elif isinstance(it, dict):
                        rid = str(it.get("replay_id") or "").strip()
                    else:
                        rid = ""
                    if rid and rid not in out:
                        out.append(rid)
                return out
    ids = data.get("replay_ids")
    if isinstance(ids, list):
        return _ids_from_any_list(ids)
    return []


def _override_lists(data: dict[str, Any], *, mode: HeroMode) -> tuple[list[str], list[str], HeroCurationConfig]:
    cfg_raw = data.get("config")
    cfg_raw = cfg_raw if isinstance(cfg_raw, dict) else {}
    weights_raw = cfg_raw.get("weights")
    weights: dict[str, float] | None = None
    if isinstance(weights_raw, dict):
        weights = {}
        for k, v in weights_raw.items():
            if not isinstance(k, str):
                continue
            try:
                weights[k] = float(v)
            except Exception:  # noqa: BLE001
                continue

    cfg = HeroCurationConfig(
        window_days=int(cfg_raw.get("window_days") or 14),
        max_items=int(cfg_raw.get("max_items") or 5),
        max_per_user=int(cfg_raw.get("max_per_user") or 2),
        min_views=int(cfg_raw.get("min_views") or 10),
        min_completions=int(cfg_raw.get("min_completions") or 2),
        min_completion_rate=float(cfg_raw.get("min_completion_rate") or 0.2),
        half_life_days=float(cfg_raw.get("half_life_days") or 5.0),
        weights=weights,
    )

    by_mode = data.get("by_mode")
    if isinstance(by_mode, dict):
        entry = by_mode.get(str(mode))
        if isinstance(entry, dict):
            pin = _ids_from_any_list(entry.get("pin"))
            exclude = _ids_from_any_list(entry.get("exclude"))
            return pin, exclude, cfg

    # Legacy formats (flat pin/exclude lists).
    pin = _ids_from_any_list(data.get("pin"))
    exclude = _ids_from_any_list(data.get("exclude"))
    return pin, exclude, cfg


def load_hero_replay_ids(
    *,
    mode: HeroMode,
    backend: StorageBackend | None = None,
) -> list[str]:
    """
    Runtime hero list: override pins first, then auto list, then (legacy) ops/hero_clips.json.
    """
    backend = backend or get_storage_backend()
    override = load_hero_override(backend=backend)
    pinned, excluded, cfg = _override_lists(override, mode=mode)

    auto = _load_ops_json(backend, "ops/hero_clips.auto.json")
    auto_ids = _ids_from_auto(auto, mode=mode)

    legacy = _load_ops_json(backend, "ops/hero_clips.json")
    legacy_ids = _ids_from_auto(legacy, mode=mode)

    merged: list[str] = []
    for rid in [*pinned, *auto_ids, *legacy_ids]:
        if not rid:
            continue
        if rid in excluded:
            continue
        if rid not in merged:
            merged.append(rid)
        if len(merged) >= int(cfg.max_items or 5):
            break
    return merged


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _decay(*, now: datetime, created_at: datetime, half_life_days: float) -> float:
    created_at = _as_aware(created_at) or now
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    try:
        return math.exp(-age_days / max(0.1, float(half_life_days)))
    except Exception:  # noqa: BLE001
        return 0.0


def compute_wow_score(
    *,
    now: datetime,
    created_at: datetime,
    engagement: dict[str, float],
    features: dict[str, float],
    half_life_days: float,
    weights: dict[str, float],
) -> float:
    def _log1p(x: float) -> float:
        try:
            return math.log1p(max(0.0, float(x)))
        except Exception:  # noqa: BLE001
            return 0.0

    completion_rate = 0.0
    try:
        views = float(engagement.get("views") or 0.0)
        completions = float(engagement.get("completions") or 0.0)
        completion_rate = completions / max(1.0, views)
    except Exception:  # noqa: BLE001
        completion_rate = 0.0

    score = 0.0
    score += float(weights.get("views", 0.0)) * _log1p(float(engagement.get("views") or 0.0))
    score += float(weights.get("completions", 0.0)) * _log1p(float(engagement.get("completions") or 0.0))
    score += float(weights.get("completion_rate", 0.0)) * float(completion_rate)
    score += float(weights.get("share_open", 0.0)) * _log1p(float(engagement.get("share_open") or 0.0))
    score += float(weights.get("clip_share", 0.0)) * _log1p(float(engagement.get("clip_share") or 0.0))
    score += float(weights.get("beat_this_click", 0.0)) * _log1p(float(engagement.get("beat_this_click") or 0.0))
    score += float(weights.get("reply_clip_shared", 0.0)) * _log1p(float(engagement.get("reply_clip_shared") or 0.0))
    score += float(weights.get("reactions", 0.0)) * _log1p(float(engagement.get("reactions") or 0.0))

    score += float(weights.get("highlight_count", 0.0)) * float(features.get("highlight_count") or 0.0)
    score += float(weights.get("damage_spikes", 0.0)) * float(features.get("damage_spikes") or 0.0)
    score += float(weights.get("badge_perfect", 0.0)) * float(features.get("badge_perfect") or 0.0)
    score += float(weights.get("badge_one_shot", 0.0)) * float(features.get("badge_one_shot") or 0.0)
    score += float(weights.get("badge_clutch", 0.0)) * float(features.get("badge_clutch") or 0.0)

    return score * _decay(now=now, created_at=created_at, half_life_days=half_life_days)


def _replay_features(payload: dict[str, Any]) -> dict[str, float]:
    highlights = payload.get("highlights")
    highlight_count = int(len(highlights)) if isinstance(highlights, list) else 0
    highlight_count = max(0, min(12, highlight_count))

    damage_spikes = 0
    if isinstance(highlights, list):
        for h in highlights:
            if not isinstance(h, dict):
                continue
            tags = h.get("tags")
            if not isinstance(tags, list):
                continue
            if any(str(t).startswith("type:damage_spike") for t in tags):
                damage_spikes += 1
    damage_spikes = max(0, min(6, int(damage_spikes)))

    end = payload.get("end_summary") if isinstance(payload.get("end_summary"), dict) else {}
    winner = str(end.get("winner") or "")
    duration_ticks = int(end.get("duration_ticks") or 0)
    hp_a = int(end.get("hp_a") or 0)
    max_a = 0
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    units = header.get("units") if isinstance(header.get("units"), list) else []
    for u in units:
        if isinstance(u, dict) and str(u.get("team") or "") == "A":
            max_a += int(u.get("max_hp") or 0)

    badge_perfect = 0.0
    badge_one_shot = 0.0
    badge_clutch = 0.0
    if winner == "A":
        if max_a > 0 and hp_a == max_a:
            badge_perfect = 1.0
        elif duration_ticks > 0 and duration_ticks <= 90:
            badge_one_shot = 1.0
        else:
            # "Clutch" fallback for wins that aren't perfect/one-shot.
            badge_clutch = 1.0

    return {
        "highlight_count": float(highlight_count),
        "damage_spikes": float(damage_spikes),
        "badge_perfect": float(badge_perfect),
        "badge_one_shot": float(badge_one_shot),
        "badge_clutch": float(badge_clutch),
    }


def recompute_hero_clips(
    session: Session,
    *,
    now: datetime | None = None,
    backend: StorageBackend | None = None,
) -> dict[str, Any]:
    """
    Computes hero clip candidates and writes:
    - ops/hero_clips.auto.json
    - ops/hero_clips.json (merged list for compatibility)
    Does NOT overwrite ops/hero_clips.override.json (but ensures it exists).
    """
    backend = backend or get_storage_backend()
    now_dt = now or datetime.now(UTC)
    settings = Settings()
    ruleset = str(settings.ruleset_version)

    ensure_hero_override_exists(backend=backend, now=now_dt)
    override = load_hero_override(backend=backend)
    cfg_by_mode: dict[str, HeroCurationConfig] = {}
    pins_by_mode: dict[str, list[str]] = {}
    excludes_by_mode: dict[str, list[str]] = {}
    for mode in ("1v1", "team"):
        pin, exc, cfg = _override_lists(override, mode=mode)  # type: ignore[arg-type]
        cfg_by_mode[mode] = cfg
        pins_by_mode[mode] = pin
        excludes_by_mode[mode] = exc

    window_days = max(1, int(cfg_by_mode["1v1"].window_days or 14))
    since = now_dt - timedelta(days=window_days)

    # Exclusions: moderation hides, open reports, soft-banned users.
    hidden_ids = {
        str(rid)
        for rid in session.scalars(
            select(ModerationHide.target_id).where(ModerationHide.target_type == "clip")
        ).all()
        if rid
    }
    reported_ids = {
        str(r.target_id)
        for r in session.scalars(
            select(Report)
            .where(Report.target_type == "clip")
            .where(Report.status == "open")
        ).all()
        if r and r.target_id
    }
    excluded_replay_ids = set(hidden_ids) | set(reported_ids)

    banned_user_ids = {
        str(r.user_id)
        for r in session.scalars(
            select(UserSoftBan).where(UserSoftBan.banned_until > now_dt)
        ).all()
        if r and r.user_id
    }

    # Candidate replays (last window days), oversampled by recency.
    max_candidates = 2000
    rows = session.execute(
        select(Match, Replay)
        .join(Replay, Replay.match_id == Match.id)
        .where(Match.status == "done")
        .where(Match.ruleset_version == ruleset)
        .where(Match.created_at >= since)
        .order_by(desc(Match.created_at), desc(Match.id))
        .limit(max_candidates)
    ).all()

    candidates: dict[str, dict[str, Any]] = {}
    for m, r in rows:
        rid = str(r.id)
        uid = str(m.user_a_id or "")
        mode = str(m.mode or "")
        if mode not in ("1v1", "team"):
            continue
        if not rid or rid in excluded_replay_ids:
            continue
        if uid and uid in banned_user_ids:
            continue
        candidates[rid] = {
            "replay_id": rid,
            "match_id": str(m.id),
            "user_id": uid or None,
            "mode": mode,
            "created_at": _as_aware(m.created_at) or now_dt,
            "artifact_path": str(r.artifact_path),
        }

    candidate_ids = set(candidates.keys())
    # Engagement aggregation from events (window).
    event_types = {
        "clip_view",
        "clip_completion",
        "clip_share",
        "share_open",
        "beat_this_click",
        "reply_clip_shared",
    }
    events = session.scalars(
        select(Event)
        .where(Event.created_at >= since)
        .where(Event.type.in_(sorted(event_types)))
        .order_by(Event.created_at.asc())
        .limit(200_000)
    ).all()

    def _payload(ev: Event) -> dict[str, Any]:
        try:
            obj = orjson.loads(ev.payload_json or "{}")
        except Exception:  # noqa: BLE001
            return {}
        return obj if isinstance(obj, dict) else {}

    def _rid_from_event(ev: Event, p: dict[str, Any]) -> str:
        t = str(ev.type)
        if t == "reply_clip_shared":
            meta = p.get("meta")
            if isinstance(meta, dict):
                pr = str(meta.get("parent_replay_id") or meta.get("replay_id") or "").strip()
                if pr:
                    return pr
            return ""
        if t == "share_open":
            rid = str(p.get("replay_id") or "").strip()
            return rid
        if t == "beat_this_click":
            rid = str(p.get("replay_id") or "").strip()
            return rid
        rid = str(p.get("replay_id") or "").strip()
        return rid

    engagement_by_rid: dict[str, dict[str, float]] = {}
    for ev in events:
        p = _payload(ev)
        rid = _rid_from_event(ev, p)
        if not rid or rid not in candidate_ids:
            continue
        row = engagement_by_rid.setdefault(
            rid,
            {
                "views": 0.0,
                "completions": 0.0,
                "clip_share": 0.0,
                "share_open": 0.0,
                "beat_this_click": 0.0,
                "reply_clip_shared": 0.0,
            },
        )
        if str(ev.type) == "clip_view":
            row["views"] += 1.0
        elif str(ev.type) == "clip_completion":
            row["completions"] += 1.0
        elif str(ev.type) == "clip_share":
            row["clip_share"] += 1.0
        elif str(ev.type) == "share_open":
            row["share_open"] += 1.0
        elif str(ev.type) == "beat_this_click":
            row["beat_this_click"] += 1.0
        elif str(ev.type) == "reply_clip_shared":
            row["reply_clip_shared"] += 1.0

    # Reactions (window).
    rx_rows = session.execute(
        select(ReplayReaction.replay_id, func.count(ReplayReaction.id))
        .where(ReplayReaction.created_at >= since)
        .where(ReplayReaction.replay_id.in_(sorted(candidate_ids)))
        .group_by(ReplayReaction.replay_id)
    ).all()
    reactions_by_rid = {str(rid): int(cnt or 0) for rid, cnt in rx_rows if rid}

    # Compute wow_score per candidate (per mode).
    auto_by_mode: dict[str, list[dict[str, Any]]] = {"1v1": [], "team": []}
    weights = dict(DEFAULT_WOW_WEIGHTS)
    w_override = cfg_by_mode["1v1"].weights or {}
    for k, v in w_override.items():
        try:
            weights[str(k)] = float(v)
        except Exception:  # noqa: BLE001
            continue

    for rid, c in candidates.items():
        mode = str(c.get("mode") or "")
        if mode not in ("1v1", "team"):
            continue
        created_at = c.get("created_at")
        created_at = created_at if isinstance(created_at, datetime) else now_dt

        engagement = dict(engagement_by_rid.get(rid, {}))
        engagement["reactions"] = float(reactions_by_rid.get(rid, 0))

        views = int(engagement.get("views") or 0)
        completions = int(engagement.get("completions") or 0)
        completion_rate = completions / max(1, views)
        cfg = cfg_by_mode[mode]
        if views < int(cfg.min_views or 0):
            continue
        if completions < int(cfg.min_completions or 0):
            continue
        if float(completion_rate) < float(cfg.min_completion_rate or 0.0):
            continue

        payload = load_replay_json(artifact_path=str(c.get("artifact_path") or ""))
        payload = payload if isinstance(payload, dict) else {}
        features = _replay_features(payload)

        wow_score = compute_wow_score(
            now=now_dt,
            created_at=created_at,
            engagement=engagement,
            features=features,
            half_life_days=float(cfg.half_life_days),
            weights=weights,
        )
        auto_by_mode[mode].append(
            {
                "replay_id": rid,
                "match_id": str(c.get("match_id") or ""),
                "user_id": c.get("user_id"),
                "created_at": created_at.isoformat(),
                "wow_score": float(wow_score),
                "engagement": {
                    **{k: int(v) for k, v in engagement.items() if k != "reactions"},
                    "reactions": int(engagement.get("reactions") or 0),
                    "completion_rate": float(completion_rate),
                },
                "features": features,
            }
        )

    # Sort + enforce per-user cap + apply override pin/exclude + take top N.
    final_by_mode: dict[str, list[str]] = {"1v1": [], "team": []}
    for mode in ("1v1", "team"):
        cfg = cfg_by_mode[mode]
        pinned = [rid for rid in pins_by_mode.get(mode, []) if rid and rid not in excluded_replay_ids]
        excluded = set(excludes_by_mode.get(mode, [])) | excluded_replay_ids

        scored = auto_by_mode[mode]
        scored.sort(
            key=lambda it: (
                -float(it.get("wow_score") or 0.0),
                str(it.get("replay_id") or ""),
            )
        )
        auto_ids_ranked = [str(it.get("replay_id") or "") for it in scored if str(it.get("replay_id") or "")]

        # Resolve user ids for pinned + auto to enforce max_per_user.
        candidates_for_user = [*pinned, *auto_ids_ranked]
        resolved_user_by_replay: dict[str, str] = {}
        if candidates_for_user:
            pairs = session.execute(
                select(Replay.id, Match.user_a_id)
                .join(Match, Match.id == Replay.match_id)
                .where(Replay.id.in_(list({r for r in candidates_for_user if r})))
            ).all()
            resolved_user_by_replay = {str(rid): str(uid or "") for rid, uid in pairs}

        per_user: dict[str, int] = {}
        merged: list[str] = []
        for rid in [*pinned, *auto_ids_ranked]:
            if not rid or rid in excluded:
                continue
            if rid in merged:
                continue
            uid = resolved_user_by_replay.get(rid, "")
            if uid:
                cur = int(per_user.get(uid, 0))
                if cur >= int(cfg.max_per_user or 2):
                    continue
                per_user[uid] = cur + 1
            merged.append(rid)
            if len(merged) >= int(cfg.max_items or 5):
                break
        final_by_mode[mode] = merged

        # Store only top-k items in auto output to keep the file readable.
        auto_by_mode[mode] = scored[: min(200, len(scored))]

    auto_out = {
        "version": 1,
        "generated_at": now_dt.isoformat(),
        "ruleset_version": ruleset,
        "window_days": int(window_days),
        "by_mode": {
            mode: {"items": auto_by_mode[mode], "selected": final_by_mode[mode]}
            for mode in ("1v1", "team")
        },
        "weights": weights,
        "filters": {
            "min_views": int(cfg_by_mode["1v1"].min_views),
            "min_completions": int(cfg_by_mode["1v1"].min_completions),
            "min_completion_rate": float(cfg_by_mode["1v1"].min_completion_rate),
            "max_per_user": int(cfg_by_mode["1v1"].max_per_user),
            "max_items": int(cfg_by_mode["1v1"].max_items),
        },
    }
    backend.put_bytes(
        key="ops/hero_clips.auto.json",
        data=_dump_ops_json(auto_out),
        content_type=guess_content_type("hero_clips.auto.json"),
    )

    merged_out = {"by_mode": final_by_mode, "generated_at": now_dt.isoformat()}
    backend.put_bytes(
        key="ops/hero_clips.json",
        data=_dump_ops_json(merged_out),
        content_type=guess_content_type("hero_clips.json"),
    )

    try:
        log_event(
            session,
            type="ops_hero_clips_recompute",
            user_id=None,
            request=None,
            payload={
                "generated_at": now_dt.isoformat(),
                "ruleset_version": ruleset,
                "window_days": int(window_days),
                "selected": final_by_mode,
            },
            now=now_dt,
        )
        session.commit()
    except Exception:  # noqa: BLE001
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "generated_at": now_dt.isoformat(),
        "ruleset_version": ruleset,
        "window_days": int(window_days),
        "by_mode": final_by_mode,
        "keys": {
            "auto": "ops/hero_clips.auto.json",
            "override": "ops/hero_clips.override.json",
            "merged": "ops/hero_clips.json",
        },
        "candidate_count": int(len(candidates)),
    }
