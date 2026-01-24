from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
from typing import Any, Iterable

import orjson
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.models import (
    ABAssignment,
    Event,
    Experiment,
    FunnelDaily,
    Match,
    MetricsDaily,
    User,
)


FUNNEL_GROWTH_V1: str = "growth_v1"
FUNNEL_STEPS_GROWTH_V1: list[str] = [
    "share_open",
    "guest_start_success",
    "first_match_done",
    "replay_open",
    "blueprint_fork",
    "blueprint_submit",
    "ranked_done",
]

FUNNEL_SHARE_V1: str = "share_v1"
FUNNEL_STEPS_SHARE_V1: list[str] = [
    "share_open",
    "start_click",
    "guest_start_success",
    "first_replay_open",
    "ranked_queue",
    "ranked_done",
]

FUNNEL_CLIPS_V1: str = "clips_v1"
FUNNEL_STEPS_CLIPS_V1: list[str] = [
    "clip_view",
    "clip_view_3s",
    "clip_completion",
    "clip_share",
    "clip_fork_click",
    "clip_open_ranked",
    "ranked_done",
]

FUNNEL_FTUE_V1: str = "ftue_v1"
FUNNEL_STEPS_FTUE_V1: list[str] = [
    "play_open",
    "clip_view_3s",
    "beat_this_click",
    "match_done",
    "reply_clip_shared",
]

FUNNEL_REMIX_V1: str = "remix_v1"
FUNNEL_STEPS_REMIX_V1: list[str] = [
    "share_open",
    "fork_click",
    "fork_created",
    "first_match_done",
]

FUNNEL_REMIX_V2: str = "remix_v2"
FUNNEL_STEPS_REMIX_V2: list[str] = [
    "share_open",
    "beat_this_click",
    "challenge_created",
    "match_done",
    "reply_clip_shared",
]

FUNNEL_REMIX_V3: str = "remix_v3"
FUNNEL_STEPS_REMIX_V3: list[str] = [
    "share_open",
    "beat_this_click",
    "challenge_created",
    "match_done",
    "reply_clip_created",
    "reply_clip_shared",
    # Branch signals (not strictly sequential, but we want daily coverage).
    "reaction_click",
    "notification_opened",
]

FUNNEL_PLAYTEST_V1: str = "playtest_v1"
FUNNEL_STEPS_PLAYTEST_V1: list[str] = [
    "playtest_opened",
    "playtest_step_1",
    "playtest_step_2",
    "playtest_step_3",
    "playtest_step_4",
    "playtest_step_5",
    "playtest_step_6",
    "playtest_completed",
]

FUNNEL_DEMO_V1: str = "demo_v1"
FUNNEL_STEPS_DEMO_V1: list[str] = [
    "demo_run_start",
    "demo_run_done",
    "demo_kit_download",
    "demo_beat_this_click",
]

FUNNEL_DEFS: dict[str, list[str]] = {
    FUNNEL_GROWTH_V1: FUNNEL_STEPS_GROWTH_V1,
    FUNNEL_SHARE_V1: FUNNEL_STEPS_SHARE_V1,
    FUNNEL_CLIPS_V1: FUNNEL_STEPS_CLIPS_V1,
    FUNNEL_FTUE_V1: FUNNEL_STEPS_FTUE_V1,
    FUNNEL_REMIX_V1: FUNNEL_STEPS_REMIX_V1,
    FUNNEL_REMIX_V2: FUNNEL_STEPS_REMIX_V2,
    FUNNEL_REMIX_V3: FUNNEL_STEPS_REMIX_V3,
    FUNNEL_PLAYTEST_V1: FUNNEL_STEPS_PLAYTEST_V1,
    FUNNEL_DEMO_V1: FUNNEL_STEPS_DEMO_V1,
}


def _parse_range(range_raw: str) -> int:
    raw = str(range_raw or "").strip().lower()
    if raw.endswith("d"):
        raw = raw[:-1]
    try:
        days = int(raw)
    except Exception:  # noqa: BLE001
        return 7
    return max(1, min(365, days))


def _date_bounds(*, day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _safe_payload(ev: Event) -> dict[str, Any]:
    try:
        obj = orjson.loads(ev.payload_json or "{}")
    except Exception:  # noqa: BLE001
        return {}
    return obj if isinstance(obj, dict) else {}


def _subject_key(ev: Event, payload: dict[str, Any]) -> str | None:
    if ev.user_id:
        return f"u:{ev.user_id}"
    dev = payload.get("device_id")
    if isinstance(dev, str) and dev.strip():
        return f"d:{dev.strip()[:80]}"
    ip_hash = payload.get("ip_hash")
    ua_hash = payload.get("user_agent_hash")
    if isinstance(ip_hash, str) and isinstance(ua_hash, str) and ip_hash and ua_hash:
        return f"a:{ip_hash[:24]}:{ua_hash[:24]}"
    if isinstance(ip_hash, str) and ip_hash:
        return f"ip:{ip_hash[:32]}"
    return None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    q = max(0.0, min(1.0, float(q)))
    idx = int(round(q * (len(xs) - 1)))
    return xs[max(0, min(len(xs) - 1, idx))]


@dataclass(frozen=True)
class RollupResult:
    start_date: date
    end_date: date
    days: int


def rollup_growth_metrics(
    session: Session,
    *,
    days: int = 7,
    end_date: date | None = None,
    funnel_name: str = FUNNEL_GROWTH_V1,
) -> RollupResult:
    days = max(1, int(days))
    end = end_date or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)

    ruleset = Settings().ruleset_version

    for i in range(days):
        day = start + timedelta(days=i)
        start_dt, end_dt = _date_bounds(day=day)

        session.execute(delete(MetricsDaily).where(MetricsDaily.date == day))
        session.execute(delete(FunnelDaily).where(FunnelDaily.date == day))

        funnel_defs = FUNNEL_DEFS
        funnel_steps: set[str] = set()
        for steps in funnel_defs.values():
            funnel_steps.update(steps)

        events = session.scalars(
            select(Event)
            .where(Event.created_at >= start_dt)
            .where(Event.created_at < end_dt)
            .where(
                Event.type.in_(
                    [
                        "share_open",
                        "start_click",
                        "share_cta_click",
                        "guest_start_success",
                        "first_match_done",
                        "first_replay_open",
                        "replay_open",
                        "blueprint_fork",
                        "playtest_opened",
                        "playtest_step_completed",
                        "playtest_completed",
                        "blueprint_submit",
                        "ranked_queue",
                        "ranked_done",
                        "tournament_done",
                        "clip_view",
                        "clip_completion",
                        "clip_share",
                        "clip_open_ranked",
                        "clip_fork_click",
                        "clip_remix_click",
                        # Mega-hit FTUE (mobile)
                        "play_open",
                        "ftue_completed",
                        "quick_remix_click",
                        "auto_tune_click",
                        "auto_tune_success",
                        # Remix v2/v3 (reply-chain / social graph)
                        "beat_this_click",
                        "challenge_created",
                        "match_done",
                        "reply_clip_created",
                        "reply_clip_shared",
                        "reaction_click",
                        "notification_opened",
                        "quick_remix_selected",
                        "quick_remix_applied",
                        "wishlist_click",
                        "discord_click",
                    ]
                    + sorted(funnel_steps)
                )
            )
        ).all()

        unique_by_type: dict[str, set[str]] = defaultdict(set)
        count_by_type: dict[str, int] = defaultdict(int)
        for ev in events:
            count_by_type[str(ev.type)] += 1
            payload = _safe_payload(ev)
            key = _subject_key(ev, payload)
            if not key:
                continue
            unique_by_type[str(ev.type)].add(key)
            if str(ev.type) == "share_cta_click":
                unique_by_type["start_click"].add(key)
            if str(ev.type) == "clip_view":
                meta = payload.get("meta")
                if isinstance(meta, dict):
                    raw = meta.get("watched_ms")
                    try:
                        watched_ms = int(raw) if raw is not None else 0
                    except Exception:  # noqa: BLE001
                        watched_ms = 0
                    if watched_ms >= 3000:
                        unique_by_type["clip_view_3s"].add(key)
            if str(ev.type) == "playtest_step_completed":
                meta = payload.get("meta")
                if isinstance(meta, dict):
                    sid = meta.get("step_id")
                    try:
                        step_id = int(sid)
                    except Exception:  # noqa: BLE001
                        step_id = -1
                    if 1 <= step_id <= 6:
                        unique_by_type[f"playtest_step_{step_id}"].add(key)

        # Global match KPIs (ranked, all users) for this day.
        total_matches = int(
            session.scalar(
                select(func.count(Match.id))
                .where(Match.status == "done")
                .where(Match.queue_type == "ranked")
                .where(Match.created_at >= start_dt)
                .where(Match.created_at < end_dt)
                .where(Match.ruleset_version == ruleset)
            )
            or 0
        )
        human_matches = int(
            session.scalar(
                select(func.count(Match.id))
                .where(Match.status == "done")
                .where(Match.queue_type == "ranked")
                .where(Match.created_at >= start_dt)
                .where(Match.created_at < end_dt)
                .where(Match.ruleset_version == ruleset)
                .where(~Match.user_b_id.like("bot_%"))  # type: ignore[arg-type]
            )
            or 0
        )

        # Time-to-first-match (guests created today who finished a ranked match).
        guests = session.execute(
            select(User.id, User.created_at)
            .where(User.is_guest.is_(True))
            .where(User.created_at >= start_dt)
            .where(User.created_at < end_dt)
        ).all()
        guest_ids = [str(uid) for uid, _created in guests]
        created_by_user = {str(uid): created for uid, created in guests}

        deltas: list[float] = []
        if guest_ids:
            rows = session.execute(
                select(Match.user_a_id, func.min(Match.finished_at))
                .where(Match.status == "done")
                .where(Match.queue_type == "ranked")
                .where(Match.user_a_id.in_(guest_ids))  # type: ignore[arg-type]
                .group_by(Match.user_a_id)
            ).all()
            for uid, finished_at in rows:
                if not uid or not finished_at:
                    continue
                created_at = created_by_user.get(str(uid))
                if not created_at:
                    continue
                if getattr(created_at, "tzinfo", None) is None:
                    created_at = created_at.replace(tzinfo=UTC)
                if getattr(finished_at, "tzinfo", None) is None:
                    finished_at = finished_at.replace(tzinfo=UTC)
                delta = (finished_at - created_at).total_seconds()
                if delta >= 0:
                    deltas.append(float(delta))

        p50 = _percentile(deltas, 0.50)
        p90 = _percentile(deltas, 0.90)

        metrics: list[MetricsDaily] = []

        def add_metric(
            key: str, value: float, meta: dict[str, Any] | None = None
        ) -> None:
            metrics.append(
                MetricsDaily(
                    date=day,
                    key=str(key),
                    value=float(value),
                    meta_json=orjson.dumps(meta or {}).decode("utf-8"),
                )
            )

        add_metric(
            "share_open_users", float(len(unique_by_type.get("share_open", set())))
        )
        add_metric(
            "guest_start_users",
            float(len(unique_by_type.get("guest_start_success", set()))),
        )
        add_metric(
            "first_match_done_users",
            float(len(unique_by_type.get("first_match_done", set()))),
        )
        add_metric(
            "replay_open_users", float(len(unique_by_type.get("replay_open", set())))
        )
        add_metric(
            "blueprint_fork_users",
            float(len(unique_by_type.get("blueprint_fork", set()))),
        )
        add_metric(
            "playtest_opened_users",
            float(len(unique_by_type.get("playtest_opened", set()))),
        )
        add_metric(
            "play_open_users", float(len(unique_by_type.get("play_open", set())))
        )
        add_metric(
            "ftue_completed_users",
            float(len(unique_by_type.get("ftue_completed", set()))),
        )
        add_metric(
            "clip_view_3s_users",
            float(len(unique_by_type.get("clip_view_3s", set()))),
        )
        add_metric(
            "quick_remix_click_users",
            float(len(unique_by_type.get("quick_remix_click", set()))),
        )
        add_metric(
            "auto_tune_click_users",
            float(len(unique_by_type.get("auto_tune_click", set()))),
        )
        add_metric(
            "auto_tune_success_users",
            float(len(unique_by_type.get("auto_tune_success", set()))),
        )
        add_metric(
            "playtest_completed_users",
            float(len(unique_by_type.get("playtest_completed", set()))),
        )
        for step_id in range(1, 7):
            add_metric(
                f"playtest_step_{step_id}_users",
                float(len(unique_by_type.get(f"playtest_step_{step_id}", set()))),
            )
        add_metric(
            "blueprint_submit_users",
            float(len(unique_by_type.get("blueprint_submit", set()))),
        )
        add_metric(
            "ranked_done_users", float(len(unique_by_type.get("ranked_done", set())))
        )
        add_metric(
            "ranked_queue_users", float(len(unique_by_type.get("ranked_queue", set())))
        )
        add_metric(
            "start_click_users", float(len(unique_by_type.get("start_click", set())))
        )
        add_metric(
            "first_replay_open_users",
            float(len(unique_by_type.get("first_replay_open", set()))),
        )
        add_metric("clip_share_users", float(len(unique_by_type.get("clip_share", set()))))
        add_metric("fork_click_events", float(count_by_type.get("fork_click", 0)))
        add_metric("fork_created_events", float(count_by_type.get("fork_created", 0)))
        add_metric(
            "beat_this_click_users",
            float(len(unique_by_type.get("beat_this_click", set()))),
        )
        add_metric("beat_this_click_events", float(count_by_type.get("beat_this_click", 0)))
        add_metric(
            "challenge_created_users",
            float(len(unique_by_type.get("challenge_created", set()))),
        )
        add_metric(
            "challenge_created_events",
            float(count_by_type.get("challenge_created", 0)),
        )
        add_metric(
            "reply_clip_shared_users",
            float(len(unique_by_type.get("reply_clip_shared", set()))),
        )
        add_metric(
            "reply_clip_shared_events",
            float(count_by_type.get("reply_clip_shared", 0)),
        )
        add_metric(
            "reply_clip_created_users",
            float(len(unique_by_type.get("reply_clip_created", set()))),
        )
        add_metric(
            "reply_clip_created_events",
            float(count_by_type.get("reply_clip_created", 0)),
        )
        add_metric(
            "reaction_click_users",
            float(len(unique_by_type.get("reaction_click", set()))),
        )
        add_metric(
            "reaction_click_events",
            float(count_by_type.get("reaction_click", 0)),
        )
        add_metric(
            "notification_opened_users",
            float(len(unique_by_type.get("notification_opened", set()))),
        )
        add_metric(
            "notification_opened_events",
            float(count_by_type.get("notification_opened", 0)),
        )
        add_metric(
            "quick_remix_selected_users",
            float(len(unique_by_type.get("quick_remix_selected", set()))),
        )
        add_metric(
            "quick_remix_selected_events",
            float(count_by_type.get("quick_remix_selected", 0)),
        )
        add_metric(
            "quick_remix_applied_users",
            float(len(unique_by_type.get("quick_remix_applied", set()))),
        )
        add_metric(
            "quick_remix_applied_events",
            float(count_by_type.get("quick_remix_applied", 0)),
        )
        add_metric(
            "wishlist_click_users",
            float(len(unique_by_type.get("wishlist_click", set()))),
        )
        add_metric(
            "discord_click_users",
            float(len(unique_by_type.get("discord_click", set()))),
        )
        add_metric(
            "tournament_done_users",
            float(len(unique_by_type.get("tournament_done", set()))),
        )
        add_metric("matches_total", float(total_matches))
        add_metric("human_matches", float(human_matches))
        if total_matches > 0:
            add_metric("human_match_rate", float(human_matches) / float(total_matches))
        else:
            add_metric("human_match_rate", 0.0)

        if p50 is not None:
            add_metric("time_to_first_match_p50_sec", float(p50))
        if p90 is not None:
            add_metric("time_to_first_match_p90_sec", float(p90))

        session.add_all(metrics)

        funnel_rows: list[FunnelDaily] = []
        for fname, steps in funnel_defs.items():
            for step in steps:
                funnel_rows.append(
                    FunnelDaily(
                        date=day,
                        funnel_name=fname,
                        step=step,
                        users_count=int(len(unique_by_type.get(step, set()))),
                        meta_json="{}",
                    )
                )
        session.add_all(funnel_rows)
        session.commit()

    return RollupResult(start_date=start, end_date=end, days=days)


def load_metrics_series(
    session: Session, *, days: int = 7, end_date: date | None = None
) -> list[dict[str, Any]]:
    days = max(1, int(days))
    end = end_date or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)

    rows = session.scalars(
        select(MetricsDaily)
        .where(MetricsDaily.date >= start)
        .where(MetricsDaily.date <= end)
        .order_by(MetricsDaily.date.asc(), MetricsDaily.key.asc())
    ).all()

    by_date: dict[date, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_date[r.date][str(r.key)] = float(r.value or 0.0)

    out: list[dict[str, Any]] = []
    for i in range(days):
        day = start + timedelta(days=i)
        out.append({"date": day.isoformat(), "metrics": by_date.get(day, {})})
    return out


def load_funnel_summary(
    session: Session,
    *,
    funnel_name: str = FUNNEL_GROWTH_V1,
    days: int = 7,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    days = max(1, int(days))
    end = end_date or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)

    rows = session.scalars(
        select(FunnelDaily)
        .where(FunnelDaily.date >= start)
        .where(FunnelDaily.date <= end)
        .where(FunnelDaily.funnel_name == funnel_name)
    ).all()
    totals: dict[str, int] = defaultdict(int)
    for r in rows:
        totals[str(r.step)] += int(r.users_count or 0)
    steps = FUNNEL_DEFS.get(str(funnel_name), FUNNEL_STEPS_GROWTH_V1)
    return [{"step": s, "users": int(totals.get(s, 0))} for s in steps]


def load_funnel_daily_series(
    session: Session,
    *,
    funnel_name: str = FUNNEL_GROWTH_V1,
    days: int = 7,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    days = max(1, int(days))
    end = end_date or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)

    rows = session.scalars(
        select(FunnelDaily)
        .where(FunnelDaily.date >= start)
        .where(FunnelDaily.date <= end)
        .where(FunnelDaily.funnel_name == funnel_name)
    ).all()

    by_date: dict[date, dict[str, int]] = defaultdict(dict)
    for r in rows:
        by_date[r.date][str(r.step)] = int(r.users_count or 0)

    steps = FUNNEL_DEFS.get(str(funnel_name), FUNNEL_STEPS_GROWTH_V1)
    out: list[dict[str, Any]] = []
    for i in range(days):
        day = start + timedelta(days=i)
        counts = {s: int(by_date.get(day, {}).get(s, 0)) for s in steps}
        out.append({"date": day.isoformat(), "steps": counts})
    return out


def load_experiment_stats(
    session: Session,
    *,
    experiment_keys: Iterable[str] | None = None,
    days: int = 7,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    days = max(1, int(days))
    end = end_date or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    start_dt, _ = _date_bounds(day=start)
    end_dt, _ = _date_bounds(day=end + timedelta(days=1))

    exp_q = select(Experiment).order_by(Experiment.key.asc())
    if experiment_keys:
        exp_q = exp_q.where(Experiment.key.in_(list(experiment_keys)))  # type: ignore[arg-type]
    exps = session.scalars(exp_q).all()

    # Build simple per-event conversion sets (unique user ids in range).
    conversion_types = sorted(
        {
            # Share funnel.
            "share_open",
            "qr_shown",
            "start_click",
            "guest_start_success",
            "first_replay_open",
            "ranked_queue",
            "ranked_done",
            "app_open_deeplink",
            # Mobile FTUE / play.
            "play_open",
            "clip_view_3s",
            "quest_claimed",
            # Playtest.
            "playtest_opened",
            "playtest_completed",
            # Clips funnel.
            "clip_view",
            "clip_completion",
            "clip_share",
            "clip_fork_click",
            "clip_open_ranked",
            # Growth/UGC.
            "first_match_done",
            "replay_open",
            "blueprint_fork",
            "blueprint_submit",
            # Remix v2/v3 (reply-chain).
            "beat_this_click",
            "challenge_created",
            "match_done",
            "reply_clip_created",
            "reply_clip_shared",
            "reaction_click",
            "notification_opened",
            "quick_remix_selected",
            "quick_remix_applied",
            # Rewards.
            "streak_extended",
            "level_up",
            "badge_unlocked",
        }
    )
    conversions_by_type: dict[str, set[str]] = defaultdict(set)
    events = session.scalars(
        select(Event)
        .where(Event.created_at >= start_dt)
        .where(Event.created_at < end_dt)
        .where(Event.type.in_(conversion_types))
    ).all()

    def _anon_id_from_payload(payload_json: str | None) -> str | None:
        try:
            obj = orjson.loads(payload_json or "{}")
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(obj, dict):
            return None
        ip_hash = obj.get("ip_hash")
        ua_hash = obj.get("user_agent_hash")
        if not isinstance(ip_hash, str) or not isinstance(ua_hash, str):
            return None
        if not ip_hash or not ua_hash:
            return None
        seed = f"{ip_hash}|{ua_hash}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    for ev in events:
        t = str(ev.type)
        subjects: list[str] = []
        if ev.user_id:
            subjects.append(str(ev.user_id))
        anon_id = _anon_id_from_payload(ev.payload_json)
        if anon_id:
            subjects.append(anon_id)
        for sid in subjects:
            conversions_by_type[t].add(sid)
        if t == "clip_view":
            payload = _safe_payload(ev)
            meta = payload.get("meta")
            if isinstance(meta, dict):
                raw = meta.get("watched_ms")
                try:
                    watched_ms = int(raw) if raw is not None else 0
                except Exception:  # noqa: BLE001
                    watched_ms = 0
                if watched_ms >= 3000:
                    for sid in subjects:
                        conversions_by_type["clip_view_3s"].add(sid)

    primary_by_experiment = {
        # Hero-feed A/B should optimize for "quest claim" (retention-ish), not blueprint forks.
        "hero_feed_v1": "quest_claimed",
    }

    out: list[dict[str, Any]] = []
    for exp in exps:
        assigns = session.scalars(
            select(ABAssignment)
            .where(ABAssignment.experiment_key == exp.key)
            .where(ABAssignment.assigned_at >= start_dt)
            .where(ABAssignment.assigned_at < end_dt)
        ).all()
        by_variant: dict[str, list[ABAssignment]] = defaultdict(list)
        for a in assigns:
            by_variant[str(a.variant or "control")].append(a)

        variants: list[dict[str, Any]] = []
        try:
            raw = orjson.loads(exp.variants_json or "[]")
        except Exception:  # noqa: BLE001
            raw = []
        if not isinstance(raw, list):
            raw = []

        def _variant_ids() -> list[str]:
            ids: list[str] = []
            for v in raw:
                if isinstance(v, dict) and v.get("id"):
                    ids.append(str(v["id"]))
            return ids or ["control"]

        for vid in _variant_ids():
            assigned_subjects = {
                str(a.subject_id) for a in by_variant.get(vid, []) if a.subject_id
            }
            primary = str(primary_by_experiment.get(str(exp.key), "blueprint_fork"))
            converted = len([uid for uid in assigned_subjects if uid in conversions_by_type.get(primary, set())])
            denom = max(1, len(assigned_subjects))
            kpis: dict[str, Any] = {}
            for k in conversion_types:
                conv = len(
                    [
                        uid
                        for uid in assigned_subjects
                        if uid in conversions_by_type.get(k, set())
                    ]
                )
                kpis[k] = {
                    "converted": int(conv),
                    "rate": float(conv) / float(denom) if assigned_subjects else 0.0,
                }
            variants.append(
                {
                    "id": vid,
                    "assigned": len(assigned_subjects),
                    "converted": int(converted),
                    "conversion_rate": float(converted) / float(denom)
                    if assigned_subjects
                    else 0.0,
                    "kpis": kpis,
                }
            )

        out.append(
            {
                "key": exp.key,
                "status": exp.status,
                "variants": variants,
            }
        )
    return out


def load_shorts_variants(
    session: Session,
    *,
    days: int = 7,
    end_date: date | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
) -> dict[str, Any]:
    days = max(1, int(days))
    end = end_date or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    start_dt, _ = _date_bounds(day=start)
    end_dt, _ = _date_bounds(day=end + timedelta(days=1))

    event_types = [
        "share_open",
        "clip_completion",
        "clip_share",
        "start_click",
        "ranked_queue",
        "ranked_done",
        "app_open_deeplink",
    ]
    events = session.scalars(
        select(Event)
        .where(Event.created_at >= start_dt)
        .where(Event.created_at < end_dt)
        .where(Event.type.in_(event_types))
        .order_by(Event.created_at)
    ).all()

    def anon_key(payload: dict[str, Any]) -> str | None:
        ip_hash = payload.get("ip_hash")
        ua_hash = payload.get("user_agent_hash")
        if isinstance(ip_hash, str) and isinstance(ua_hash, str) and ip_hash and ua_hash:
            return f"a:{ip_hash[:24]}:{ua_hash[:24]}"
        return None

    def variants(payload: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        v = payload.get("variants")
        if isinstance(v, dict):
            for k, val in v.items():
                if isinstance(k, str) and isinstance(val, str) and val.strip():
                    out[k] = val.strip()
        meta = payload.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("variants"), dict):
            for k, val in (meta.get("variants") or {}).items():
                if (
                    isinstance(k, str)
                    and isinstance(val, str)
                    and val.strip()
                    and k not in out
                ):
                    out[k] = val.strip()
        # Legacy fallbacks.
        if "clip_len_v1" not in out:
            raw = payload.get("clip_len_variant")
            if isinstance(raw, str) and raw.strip():
                out["clip_len_v1"] = raw.strip()
        if "captions_v2" not in out:
            raw = payload.get("captions_template_id")
            if isinstance(raw, str) and raw.strip():
                out["captions_v2"] = raw.strip()
        return out

    def _utm(payload: dict[str, Any]) -> dict[str, str]:
        v = payload.get("utm")
        if isinstance(v, dict):
            out: dict[str, str] = {}
            for k, val in v.items():
                if isinstance(k, str) and isinstance(val, str) and val.strip():
                    out[k] = val.strip()[:120]
            return out
        return {}

    def _utm_match(
        payload: dict[str, Any],
        *,
        utm_medium_filter: str | None,
        utm_campaign_filter: str | None,
    ) -> bool:
        if not utm_medium_filter and not utm_campaign_filter:
            return True
        u = _utm(payload)
        if utm_medium_filter:
            if str(u.get("utm_medium") or "").strip().lower() != str(
                utm_medium_filter
            ).strip().lower():
                return False
        if utm_campaign_filter:
            if str(u.get("utm_campaign") or "").strip().lower() != str(
                utm_campaign_filter
            ).strip().lower():
                return False
        return True

    def _utm_source(payload: dict[str, Any]) -> str:
        u = _utm(payload)
        src = str(u.get("utm_source") or "").strip().lower()
        return src[:80] if src else "unknown"

    share_open_len: dict[str, set[str]] = defaultdict(set)
    share_open_cap: dict[str, set[str]] = defaultdict(set)
    completion_len: dict[str, set[str]] = defaultdict(set)
    completion_cap: dict[str, set[str]] = defaultdict(set)
    share_len: dict[str, set[str]] = defaultdict(set)
    share_cap: dict[str, set[str]] = defaultdict(set)
    start_len: dict[str, set[str]] = defaultdict(set)
    start_cap: dict[str, set[str]] = defaultdict(set)
    app_open_len: dict[str, set[str]] = defaultdict(set)
    app_open_cap: dict[str, set[str]] = defaultdict(set)

    channels: set[str] = set()
    share_open_anon_by_source: dict[str, set[str]] = defaultdict(set)
    share_open_len_by_source: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    share_open_cap_by_source: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )

    ranked_queue_by_match: dict[str, dict[str, str]] = {}
    ranked_done_match_ids: set[str] = set()

    for ev in events:
        payload = _safe_payload(ev)
        akey = anon_key(payload)
        vs = variants(payload)
        clip_len = vs.get("clip_len_v1")
        captions = vs.get("captions_v2")

        if str(ev.type) == "share_open":
            if str(payload.get("source") or "") != "s/clip":
                continue
            if not akey:
                continue
            if not _utm_match(
                payload,
                utm_medium_filter=utm_medium,
                utm_campaign_filter=utm_campaign,
            ):
                continue
            src = _utm_source(payload)
            channels.add(src)
            share_open_anon_by_source[src].add(akey)
            if clip_len:
                share_open_len[str(clip_len)].add(akey)
                share_open_len_by_source[src][str(clip_len)].add(akey)
            if captions:
                share_open_cap[str(captions)].add(akey)
                share_open_cap_by_source[src][str(captions)].add(akey)
            continue

        if str(ev.type) in {"clip_completion", "clip_share"}:
            if str(payload.get("source") or "") != "s/clip":
                continue
            if not akey:
                continue
            if str(ev.type) == "clip_completion":
                if clip_len:
                    completion_len[str(clip_len)].add(akey)
                if captions:
                    completion_cap[str(captions)].add(akey)
            else:
                if clip_len:
                    share_len[str(clip_len)].add(akey)
                if captions:
                    share_cap[str(captions)].add(akey)
            continue

        if str(ev.type) == "start_click":
            src = str(payload.get("source") or "")
            if not src.startswith("s/clip"):
                continue
            if not akey:
                continue
            if clip_len:
                start_len[str(clip_len)].add(akey)
            if captions:
                start_cap[str(captions)].add(akey)
            continue

        if str(ev.type) == "app_open_deeplink":
            if not akey:
                continue
            if clip_len:
                app_open_len[str(clip_len)].add(akey)
            if captions:
                app_open_cap[str(captions)].add(akey)
            continue

        if str(ev.type) == "ranked_queue":
            match_id = str(payload.get("match_id") or "").strip()
            if not match_id or not akey:
                continue
            ranked_queue_by_match[match_id] = {
                "anon": akey,
                "clip_len_v1": str(clip_len or "").strip(),
                "captions_v2": str(captions or "").strip(),
            }
            continue

        if str(ev.type) == "ranked_done":
            match_id = str(payload.get("match_id") or "").strip()
            if match_id:
                ranked_done_match_ids.add(match_id)
            continue

    ranked_done_len: dict[str, set[str]] = defaultdict(set)
    ranked_done_cap: dict[str, set[str]] = defaultdict(set)
    for mid in ranked_done_match_ids:
        info = ranked_queue_by_match.get(mid)
        if not info:
            continue
        akey = info.get("anon")
        if not akey:
            continue
        lv = info.get("clip_len_v1") or ""
        cv = info.get("captions_v2") or ""
        if lv:
            ranked_done_len[str(lv)].add(akey)
        if cv:
            ranked_done_cap[str(cv)].add(akey)

    def _table(
        *,
        key: str,
        bases: dict[str, set[str]],
        completion: dict[str, set[str]],
        share: dict[str, set[str]],
        start: dict[str, set[str]],
        ranked_done: dict[str, set[str]],
        app_open: dict[str, set[str]],
    ) -> dict[str, Any]:
        rows = []
        for vid in sorted(bases.keys()):
            base = bases.get(vid, set())
            denom = max(1, len(base))
            ranked_done_rate = (
                float(len(base & ranked_done.get(vid, set()))) / float(denom)
                if base
                else 0.0
            )
            rows.append(
                {
                    "id": str(vid),
                    "n": int(len(base)),
                    "completion_rate": float(len(base & completion.get(vid, set())))
                    / float(denom)
                    if base
                    else 0.0,
                    "share_rate": float(len(base & share.get(vid, set()))) / float(denom)
                    if base
                    else 0.0,
                    "start_click_rate": float(len(base & start.get(vid, set())))
                    / float(denom)
                    if base
                    else 0.0,
                    # Primary KPI: ranked_done / share_open.
                    "primary_kpi_rate": ranked_done_rate,
                    "ranked_done_rate": ranked_done_rate,
                    "app_open_deeplink_rate": float(len(base & app_open.get(vid, set())))
                    / float(denom)
                    if base
                    else 0.0,
                }
            )
        return {"key": key, "variants": rows}

    tables = [
        _table(
            key="clip_len_v1",
            bases=share_open_len,
            completion=completion_len,
            share=share_len,
            start=start_len,
            ranked_done=ranked_done_len,
            app_open=app_open_len,
        ),
        _table(
            key="captions_v2",
            bases=share_open_cap,
            completion=completion_cap,
            share=share_cap,
            start=start_cap,
            ranked_done=ranked_done_cap,
            app_open=app_open_cap,
        ),
    ]

    groups: list[dict[str, Any]] = []
    channel_rows = [(len(share_open_anon_by_source[c]), c) for c in channels]
    for _n, ch in sorted(channel_rows, key=lambda it: (-int(it[0]), str(it[1]))):
        groups.append(
            {
                "utm_source": ch,
                "n_share_open": int(len(share_open_anon_by_source[ch])),
                "tables": [
                    _table(
                        key="clip_len_v1",
                        bases=share_open_len_by_source[ch],
                        completion=completion_len,
                        share=share_len,
                        start=start_len,
                        ranked_done=ranked_done_len,
                        app_open=app_open_len,
                    ),
                    _table(
                        key="captions_v2",
                        bases=share_open_cap_by_source[ch],
                        completion=completion_cap,
                        share=share_cap,
                        start=start_cap,
                        ranked_done=ranked_done_cap,
                        app_open=app_open_cap,
                    ),
                ],
            }
        )

    selected = str(utm_source or "").strip().lower() or None
    if selected and selected != "all":
        filtered_groups = [
            g for g in groups if str(g.get("utm_source") or "") == selected
        ]
        tables = (
            list(filtered_groups[0].get("tables") or [])
            if filtered_groups
            else []
        )
        groups = filtered_groups

    available_channels = [
        c for _n, c in sorted(channel_rows, key=lambda it: (-int(it[0]), str(it[1])))
    ]

    return {
        "range": f"{days}d",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "primary_kpi": "ranked_done_per_share_open",
        "filters": {
            "utm_source": selected,
            "utm_medium": str(utm_medium or "").strip().lower() or None,
            "utm_campaign": str(utm_campaign or "").strip().lower() or None,
        },
        "available_channels": available_channels,
        "groups": groups,
        "tables": tables,
    }
