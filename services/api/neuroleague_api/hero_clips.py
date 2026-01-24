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
    reliability_view_n_min: int = 50
    completion_wilson_z: float = 1.0
    half_life_days: float = 5.0
    diversity_max_per_synergy: int = 2
    diversity_max_per_portal: int = 1
    diversity_max_per_creature: int = 1
    diversity_penalty_user: float = 2.0
    diversity_penalty_synergy: float = 1.0
    diversity_penalty_portal: float = 0.8
    diversity_penalty_creature: float = 1.2
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
        "version": 2,
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
            "reliability_view_n_min": 50,
            "completion_wilson_z": 1.0,
            "half_life_days": 5.0,
            "diversity_max_per_synergy": 2,
            "diversity_max_per_portal": 1,
            "diversity_max_per_creature": 1,
            "diversity_penalty_user": 2.0,
            "diversity_penalty_synergy": 1.0,
            "diversity_penalty_portal": 0.8,
            "diversity_penalty_creature": 1.2,
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
            selected = cur.get("selected")
            if isinstance(selected, list):
                return _ids_from_any_list(selected)
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
        reliability_view_n_min=int(cfg_raw.get("reliability_view_n_min") or 50),
        completion_wilson_z=float(cfg_raw.get("completion_wilson_z") or 1.0),
        half_life_days=float(cfg_raw.get("half_life_days") or 5.0),
        diversity_max_per_synergy=int(cfg_raw.get("diversity_max_per_synergy") or 2),
        diversity_max_per_portal=int(cfg_raw.get("diversity_max_per_portal") or 1),
        diversity_max_per_creature=int(cfg_raw.get("diversity_max_per_creature") or 1),
        diversity_penalty_user=float(cfg_raw.get("diversity_penalty_user") or 2.0),
        diversity_penalty_synergy=float(cfg_raw.get("diversity_penalty_synergy") or 1.0),
        diversity_penalty_portal=float(cfg_raw.get("diversity_penalty_portal") or 0.8),
        diversity_penalty_creature=float(cfg_raw.get("diversity_penalty_creature") or 1.2),
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
    reliability_view_n_min: int = 50,
    completion_wilson_z: float = 1.0,
) -> float:
    breakdown = compute_wow_breakdown(
        now=now,
        created_at=created_at,
        engagement=engagement,
        features=features,
        half_life_days=half_life_days,
        weights=weights,
        reliability_view_n_min=reliability_view_n_min,
        completion_wilson_z=completion_wilson_z,
    )
    return float(breakdown.get("wow_score") or 0.0)


def _wilson_lower_bound(*, successes: float, trials: float, z: float) -> float:
    try:
        n = float(trials)
        if n <= 0:
            return 0.0
        k = max(0.0, min(n, float(successes)))
        z = max(0.0, float(z))
        p_hat = k / n
        denom = 1.0 + (z * z) / n
        center = p_hat + (z * z) / (2.0 * n)
        adj = z * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z * z) / (4.0 * n * n))
        lower = (center - adj) / denom
        return max(0.0, min(1.0, float(lower)))
    except Exception:  # noqa: BLE001
        return 0.0


def compute_wow_breakdown(
    *,
    now: datetime,
    created_at: datetime,
    engagement: dict[str, float],
    features: dict[str, float],
    half_life_days: float,
    weights: dict[str, float],
    reliability_view_n_min: int = 50,
    completion_wilson_z: float = 1.0,
) -> dict[str, float]:
    def _log1p(x: float) -> float:
        try:
            return math.log1p(max(0.0, float(x)))
        except Exception:  # noqa: BLE001
            return 0.0

    completion_rate = 0.0
    completion_rate_wilson = 0.0
    try:
        views = float(engagement.get("views") or 0.0)
        completions = float(engagement.get("completions") or 0.0)
        completion_rate = completions / max(1.0, views)
        completion_rate_wilson = _wilson_lower_bound(
            successes=completions,
            trials=views,
            z=completion_wilson_z,
        )
    except Exception:  # noqa: BLE001
        completion_rate = 0.0
        completion_rate_wilson = 0.0

    reliability_factor = 1.0
    try:
        views_n = max(0.0, float(engagement.get("views") or 0.0))
        n_min = max(1.0, float(reliability_view_n_min))
        reliability_factor = min(1.0, views_n / n_min)
    except Exception:  # noqa: BLE001
        reliability_factor = 1.0

    engagement_score = 0.0
    engagement_score += float(weights.get("views", 0.0)) * _log1p(
        float(engagement.get("views") or 0.0)
    )
    engagement_score += float(weights.get("completions", 0.0)) * _log1p(
        float(engagement.get("completions") or 0.0)
    )
    engagement_score += float(weights.get("completion_rate", 0.0)) * float(
        completion_rate_wilson
    )
    engagement_score += float(weights.get("share_open", 0.0)) * _log1p(
        float(engagement.get("share_open") or 0.0)
    )
    engagement_score += float(weights.get("clip_share", 0.0)) * _log1p(
        float(engagement.get("clip_share") or 0.0)
    )
    engagement_score += float(weights.get("beat_this_click", 0.0)) * _log1p(
        float(engagement.get("beat_this_click") or 0.0)
    )
    engagement_score += float(weights.get("reply_clip_shared", 0.0)) * _log1p(
        float(engagement.get("reply_clip_shared") or 0.0)
    )
    engagement_score += float(weights.get("reactions", 0.0)) * _log1p(
        float(engagement.get("reactions") or 0.0)
    )

    feature_score = 0.0
    feature_score += float(weights.get("highlight_count", 0.0)) * float(
        features.get("highlight_count") or 0.0
    )
    feature_score += float(weights.get("damage_spikes", 0.0)) * float(
        features.get("damage_spikes") or 0.0
    )
    feature_score += float(weights.get("badge_perfect", 0.0)) * float(
        features.get("badge_perfect") or 0.0
    )
    feature_score += float(weights.get("badge_one_shot", 0.0)) * float(
        features.get("badge_one_shot") or 0.0
    )
    feature_score += float(weights.get("badge_clutch", 0.0)) * float(
        features.get("badge_clutch") or 0.0
    )

    decay = _decay(now=now, created_at=created_at, half_life_days=half_life_days)
    base_score = float(engagement_score) * float(reliability_factor) + float(
        feature_score
    )
    return {
        "completion_rate": float(completion_rate),
        "completion_rate_wilson": float(completion_rate_wilson),
        "reliability_factor": float(reliability_factor),
        "decay": float(decay),
        "engagement_score": float(engagement_score),
        "feature_score": float(feature_score),
        "base_score": float(base_score),
        "wow_score": float(base_score) * float(decay),
    }


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


def _replay_diversity(payload: dict[str, Any]) -> dict[str, Any]:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    portal_id = str(header.get("portal_id") or "").strip() or None
    units = header.get("units") if isinstance(header.get("units"), list) else []
    team_a: list[dict[str, Any]] = []
    for u in units:
        if isinstance(u, dict) and str(u.get("team") or "") == "A":
            team_a.append(u)
    team_a.sort(
        key=lambda u: (
            int(u.get("slot_index") or 0),
            str(u.get("unit_id") or ""),
            str(u.get("creature_id") or ""),
        )
    )

    creatures: list[str] = []
    tag_counts: dict[str, int] = {}
    for u in team_a:
        cid = str(u.get("creature_id") or "").strip()
        if cid:
            creatures.append(cid)
        tags = u.get("tags")
        if isinstance(tags, list):
            for t in tags:
                ts = str(t or "").strip()
                if not ts:
                    continue
                tag_counts[ts] = int(tag_counts.get(ts, 0)) + 1

    primary_synergy: str | None = None
    if tag_counts:
        primary_synergy = sorted(tag_counts.items(), key=lambda kv: (-int(kv[1]), kv[0]))[0][0]

    return {
        "portal_id": portal_id,
        "primary_synergy": primary_synergy,
        "creatures": creatures[:4],
        "primary_creature": creatures[0] if creatures else None,
    }


def _diversity_penalty(
    *,
    meta: dict[str, Any],
    counts_user: dict[str, int],
    counts_synergy: dict[str, int],
    counts_portal: dict[str, int],
    counts_creature: dict[str, int],
    cfg: HeroCurationConfig,
    enforce_caps: bool,
) -> tuple[float, dict[str, Any], bool]:
    uid = str(meta.get("user_id") or "").strip()
    synergy = str(meta.get("primary_synergy") or "").strip()
    portal = str(meta.get("portal_id") or "").strip()
    creature = str(meta.get("primary_creature") or "").strip()

    cur_user = int(counts_user.get(uid, 0)) if uid else 0
    cur_syn = int(counts_synergy.get(synergy, 0)) if synergy else 0
    cur_portal = int(counts_portal.get(portal, 0)) if portal else 0
    cur_creature = int(counts_creature.get(creature, 0)) if creature else 0

    if enforce_caps:
        if uid and cur_user >= int(cfg.max_per_user or 2):
            return 0.0, {"blocked": "max_per_user", "value": uid}, True
        if synergy and cur_syn >= int(cfg.diversity_max_per_synergy or 2):
            return 0.0, {"blocked": "max_per_synergy", "value": synergy}, True
        if portal and cur_portal >= int(cfg.diversity_max_per_portal or 1):
            return 0.0, {"blocked": "max_per_portal", "value": portal}, True
        if creature and cur_creature >= int(cfg.diversity_max_per_creature or 1):
            return 0.0, {"blocked": "max_per_creature", "value": creature}, True

    penalty = 0.0
    reasons: dict[str, Any] = {"overlaps": {}}
    if uid and cur_user > 0:
        delta = float(cfg.diversity_penalty_user) * float(cur_user)
        penalty += delta
        reasons["overlaps"]["user_id"] = {
            "value": uid,
            "count": cur_user,
            "penalty": float(delta),
        }
    if synergy and cur_syn > 0:
        delta = float(cfg.diversity_penalty_synergy) * float(cur_syn)
        penalty += delta
        reasons["overlaps"]["synergy"] = {
            "value": synergy,
            "count": cur_syn,
            "penalty": float(delta),
        }
    if portal and cur_portal > 0:
        delta = float(cfg.diversity_penalty_portal) * float(cur_portal)
        penalty += delta
        reasons["overlaps"]["portal_id"] = {
            "value": portal,
            "count": cur_portal,
            "penalty": float(delta),
        }
    if creature and cur_creature > 0:
        delta = float(cfg.diversity_penalty_creature) * float(cur_creature)
        penalty += delta
        reasons["overlaps"]["creature_id"] = {
            "value": creature,
            "count": cur_creature,
            "penalty": float(delta),
        }
    reasons["penalty_total"] = float(penalty)
    return float(penalty), reasons, False


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
                "views_total": 0.0,
                "completions": 0.0,
                "clip_share": 0.0,
                "share_open": 0.0,
                "beat_this_click": 0.0,
                "reply_clip_shared": 0.0,
            },
        )
        if str(ev.type) == "clip_view":
            row["views_total"] += 1.0
            watched_ms = 0
            meta = p.get("meta")
            if isinstance(meta, dict):
                raw = meta.get("watched_ms")
                try:
                    watched_ms = int(raw) if raw is not None else 0
                except Exception:  # noqa: BLE001
                    watched_ms = 0
            if watched_ms >= 3000:
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
        diversity = _replay_diversity(payload)
        diversity["user_id"] = c.get("user_id")

        breakdown = compute_wow_breakdown(
            now=now_dt,
            created_at=created_at,
            engagement=engagement,
            features=features,
            half_life_days=float(cfg.half_life_days),
            weights=weights,
            reliability_view_n_min=int(cfg.reliability_view_n_min or 50),
            completion_wilson_z=float(cfg.completion_wilson_z or 1.0),
        )
        wow_score = float(breakdown.get("wow_score") or 0.0)
        auto_by_mode[mode].append(
            {
                "replay_id": rid,
                "match_id": str(c.get("match_id") or ""),
                "user_id": c.get("user_id"),
                "created_at": created_at.isoformat(),
                "wow_score": float(wow_score),
                "wow_breakdown": breakdown,
                "engagement": {
                    **{k: int(v) for k, v in engagement.items() if k != "reactions"},
                    "reactions": int(engagement.get("reactions") or 0),
                    "completion_rate": float(completion_rate),
                    "completion_rate_wilson": float(breakdown.get("completion_rate_wilson") or 0.0),
                },
                "features": features,
                "diversity": diversity,
            }
        )

    # Sort + apply diversity constraints + take top N.
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

        item_by_rid: dict[str, dict[str, Any]] = {
            str(it.get("replay_id") or ""): it
            for it in scored
            if str(it.get("replay_id") or "")
        }

        pinned_meta: dict[str, dict[str, Any]] = {}
        pinned_ids = [r for r in pinned if r and r not in excluded]
        if pinned_ids:
            rows2 = session.execute(
                select(Replay.id, Match.user_a_id, Replay.artifact_path)
                .join(Match, Match.id == Replay.match_id)
                .where(Replay.id.in_(sorted(set(pinned_ids))))
            ).all()
            for rid, uid, ap in rows2:
                try:
                    payload = load_replay_json(artifact_path=str(ap or ""))
                except Exception:  # noqa: BLE001
                    payload = {}
                payload = payload if isinstance(payload, dict) else {}
                meta = _replay_diversity(payload)
                meta["user_id"] = str(uid or "").strip() or None
                pinned_meta[str(rid)] = meta

        counts_user: dict[str, int] = {}
        counts_synergy: dict[str, int] = {}
        counts_portal: dict[str, int] = {}
        counts_creature: dict[str, int] = {}

        def _inc(meta: dict[str, Any]) -> None:
            uid = str(meta.get("user_id") or "").strip()
            if uid:
                counts_user[uid] = int(counts_user.get(uid, 0)) + 1
            synergy = str(meta.get("primary_synergy") or "").strip()
            if synergy:
                counts_synergy[synergy] = int(counts_synergy.get(synergy, 0)) + 1
            portal = str(meta.get("portal_id") or "").strip()
            if portal:
                counts_portal[portal] = int(counts_portal.get(portal, 0)) + 1
            creature = str(meta.get("primary_creature") or "").strip()
            if creature:
                counts_creature[creature] = int(counts_creature.get(creature, 0)) + 1

        selected: list[str] = []

        # Start with pinned: operator override always wins.
        for rid in pinned:
            if not rid or rid in excluded or rid in selected:
                continue
            selected.append(rid)
            meta = pinned_meta.get(rid)
            if meta is None:
                it = item_by_rid.get(rid)
                meta = it.get("diversity") if isinstance(it, dict) and isinstance(it.get("diversity"), dict) else None
            if isinstance(meta, dict):
                _inc(meta)
            if len(selected) >= int(cfg.max_items or 5):
                break

        pool = [
            it
            for it in scored
            if str(it.get("replay_id") or "") and str(it.get("replay_id") or "") not in selected
        ]
        while len(selected) < int(cfg.max_items or 5):
            best: dict[str, Any] | None = None
            best_eff = -1e18
            best_base = -1e18
            best_rid = ""
            best_pen = 0.0
            best_reason: dict[str, Any] = {}

            for it in pool:
                rid = str(it.get("replay_id") or "")
                if not rid or rid in excluded or rid in selected:
                    continue
                meta = it.get("diversity") if isinstance(it.get("diversity"), dict) else {}
                meta = dict(meta) if isinstance(meta, dict) else {}
                meta.setdefault("user_id", it.get("user_id"))
                pen, reason, blocked = _diversity_penalty(
                    meta=meta,
                    counts_user=counts_user,
                    counts_synergy=counts_synergy,
                    counts_portal=counts_portal,
                    counts_creature=counts_creature,
                    cfg=cfg,
                    enforce_caps=True,
                )
                if blocked:
                    continue
                base = float(it.get("wow_score") or 0.0)
                eff = float(base) - float(pen)
                if (eff, base, rid) > (best_eff, best_base, best_rid):
                    best = it
                    best_eff = eff
                    best_base = base
                    best_rid = rid
                    best_pen = float(pen)
                    best_reason = reason

            if best is None:
                break
            rid = str(best.get("replay_id") or "")
            if not rid:
                break
            selected.append(rid)
            # Persist into the item for ops explainability.
            best["diversity_penalty_selected"] = float(best_pen)
            best["diversity_penalty_selected_detail"] = best_reason
            if isinstance(best.get("wow_breakdown"), dict):
                best["wow_breakdown"] = {
                    **best["wow_breakdown"],
                    "diversity_penalty_selected": float(best_pen),
                }
            meta = best.get("diversity") if isinstance(best.get("diversity"), dict) else {}
            meta = dict(meta) if isinstance(meta, dict) else {}
            meta.setdefault("user_id", best.get("user_id"))
            _inc(meta)
            pool = [it for it in pool if str(it.get("replay_id") or "") != rid]

        # Explainability: compute overlap penalty vs final selected set (without hard caps).
        selected_meta: dict[str, dict[str, Any]] = {}
        for rid in selected:
            if rid in pinned_meta:
                selected_meta[rid] = pinned_meta[rid]
                continue
            it = item_by_rid.get(rid)
            if it and isinstance(it.get("diversity"), dict):
                meta = dict(it["diversity"])
                meta.setdefault("user_id", it.get("user_id"))
                selected_meta[rid] = meta

        total_user: dict[str, int] = {}
        total_syn: dict[str, int] = {}
        total_portal: dict[str, int] = {}
        total_creature: dict[str, int] = {}
        for meta in selected_meta.values():
            uid = str(meta.get("user_id") or "").strip()
            if uid:
                total_user[uid] = int(total_user.get(uid, 0)) + 1
            syn = str(meta.get("primary_synergy") or "").strip()
            if syn:
                total_syn[syn] = int(total_syn.get(syn, 0)) + 1
            portal = str(meta.get("portal_id") or "").strip()
            if portal:
                total_portal[portal] = int(total_portal.get(portal, 0)) + 1
            creature = str(meta.get("primary_creature") or "").strip()
            if creature:
                total_creature[creature] = int(total_creature.get(creature, 0)) + 1

        for it in scored[: min(200, len(scored))]:
            rid = str(it.get("replay_id") or "")
            meta = it.get("diversity") if isinstance(it.get("diversity"), dict) else {}
            meta = dict(meta) if isinstance(meta, dict) else {}
            meta.setdefault("user_id", it.get("user_id"))

            uid = str(meta.get("user_id") or "").strip()
            syn = str(meta.get("primary_synergy") or "").strip()
            portal = str(meta.get("portal_id") or "").strip()
            creature = str(meta.get("primary_creature") or "").strip()

            # Exclude self contribution if the item is already selected.
            self_uid = ""
            self_syn = ""
            self_portal = ""
            self_creature = ""
            if rid in selected_meta:
                m0 = selected_meta[rid]
                self_uid = str(m0.get("user_id") or "").strip()
                self_syn = str(m0.get("primary_synergy") or "").strip()
                self_portal = str(m0.get("portal_id") or "").strip()
                self_creature = str(m0.get("primary_creature") or "").strip()

            overlap_user = max(0, int(total_user.get(uid, 0)) - (1 if uid and uid == self_uid else 0)) if uid else 0
            overlap_syn = max(0, int(total_syn.get(syn, 0)) - (1 if syn and syn == self_syn else 0)) if syn else 0
            overlap_portal = max(0, int(total_portal.get(portal, 0)) - (1 if portal and portal == self_portal else 0)) if portal else 0
            overlap_creature = max(0, int(total_creature.get(creature, 0)) - (1 if creature and creature == self_creature else 0)) if creature else 0

            pen = 0.0
            detail: dict[str, Any] = {"overlaps": {}}
            if uid and overlap_user > 0:
                delta = float(cfg.diversity_penalty_user) * float(overlap_user)
                pen += delta
                detail["overlaps"]["user_id"] = {"value": uid, "count": overlap_user, "penalty": float(delta)}
            if syn and overlap_syn > 0:
                delta = float(cfg.diversity_penalty_synergy) * float(overlap_syn)
                pen += delta
                detail["overlaps"]["synergy"] = {"value": syn, "count": overlap_syn, "penalty": float(delta)}
            if portal and overlap_portal > 0:
                delta = float(cfg.diversity_penalty_portal) * float(overlap_portal)
                pen += delta
                detail["overlaps"]["portal_id"] = {"value": portal, "count": overlap_portal, "penalty": float(delta)}
            if creature and overlap_creature > 0:
                delta = float(cfg.diversity_penalty_creature) * float(overlap_creature)
                pen += delta
                detail["overlaps"]["creature_id"] = {"value": creature, "count": overlap_creature, "penalty": float(delta)}
            detail["penalty_total"] = float(pen)

            it["diversity_penalty_vs_selected"] = float(pen)
            it["diversity_penalty_vs_selected_detail"] = detail

        final_by_mode[mode] = selected

        # Store only top-k items in auto output to keep the file readable.
        auto_by_mode[mode] = scored[: min(200, len(scored))]

    auto_out = {
        "version": 2,
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
            "reliability_view_n_min": int(cfg_by_mode["1v1"].reliability_view_n_min),
            "completion_wilson_z": float(cfg_by_mode["1v1"].completion_wilson_z),
            "max_per_user": int(cfg_by_mode["1v1"].max_per_user),
            "max_items": int(cfg_by_mode["1v1"].max_items),
            "diversity_max_per_synergy": int(cfg_by_mode["1v1"].diversity_max_per_synergy),
            "diversity_max_per_portal": int(cfg_by_mode["1v1"].diversity_max_per_portal),
            "diversity_max_per_creature": int(cfg_by_mode["1v1"].diversity_max_per_creature),
            "diversity_penalty_user": float(cfg_by_mode["1v1"].diversity_penalty_user),
            "diversity_penalty_synergy": float(cfg_by_mode["1v1"].diversity_penalty_synergy),
            "diversity_penalty_portal": float(cfg_by_mode["1v1"].diversity_penalty_portal),
            "diversity_penalty_creature": float(cfg_by_mode["1v1"].diversity_penalty_creature),
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
