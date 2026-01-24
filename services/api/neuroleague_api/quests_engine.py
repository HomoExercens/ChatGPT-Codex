from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

import orjson
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import Event, Quest, QuestAssignment, QuestEventApplied
from neuroleague_api.storage_backend import get_storage_backend, guess_content_type


Cadence = Literal["daily", "weekly"]

KST = ZoneInfo("Asia/Seoul")

QUESTS_OVERRIDE_KEY = "ops/quests_override.json"


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def kst_today_key(*, now_utc: datetime | None = None) -> str:
    now = _as_aware_utc(now_utc) or datetime.now(UTC)
    return now.astimezone(KST).date().strftime("%Y-%m-%d")


def kst_week_key(*, now_utc: datetime | None = None) -> str:
    now = _as_aware_utc(now_utc) or datetime.now(UTC)
    kst_date = now.astimezone(KST).date()
    year, week, _ = kst_date.isocalendar()
    return f"{int(year)}W{int(week):02d}"


def _seed(*, cadence: Cadence, period_key: str, ruleset_version: str) -> str:
    return f"{cadence}|{period_key}|{ruleset_version}"


def _hash_choice(*, seed: str, key: str) -> str:
    return hashlib.sha256(f"{seed}|{key}".encode("utf-8")).hexdigest()


def _filter_active(*, q: Quest, now: datetime) -> bool:
    now = _as_aware_utc(now) or datetime.now(UTC)
    start = _as_aware_utc(q.active_from)
    end = _as_aware_utc(q.active_to)
    if start is not None and start > now:
        return False
    if end is not None and end <= now:
        return False
    return True


def load_quest_overrides() -> dict[str, Any]:
    backend = get_storage_backend()
    if not backend.exists(key=QUESTS_OVERRIDE_KEY):
        return {}
    try:
        raw = backend.get_bytes(key=QUESTS_OVERRIDE_KEY)
        parsed = orjson.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def write_quest_overrides(payload: dict[str, Any]) -> None:
    backend = get_storage_backend()
    backend.put_bytes(
        key=QUESTS_OVERRIDE_KEY,
        data=orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS),
        content_type=guess_content_type("quests_override.json"),
    )


def _override_keys_for(
    *, overrides: dict[str, Any], cadence: Cadence, period_key: str
) -> list[str] | None:
    raw = overrides.get(str(cadence))
    if not isinstance(raw, dict):
        return None
    if str(raw.get("period_key") or "") != str(period_key):
        return None
    keys = raw.get("quest_keys")
    if not isinstance(keys, list):
        return None
    out = [str(k) for k in keys if isinstance(k, (str, int, float))]
    return [k for k in out if k.strip()]


def select_quests_for_period(
    session: Session,
    *,
    cadence: Cadence,
    period_key: str,
    limit: int,
    now: datetime | None = None,
    overrides: dict[str, Any] | None = None,
) -> list[Quest]:
    now_dt = _as_aware_utc(now) or datetime.now(UTC)
    settings = Settings()
    ruleset = str(settings.ruleset_version)

    quests = session.scalars(select(Quest).where(Quest.cadence == str(cadence))).all()
    active = [q for q in quests if _filter_active(q=q, now=now_dt)]
    by_key = {str(q.key): q for q in active}

    order: list[Quest] = []
    override_keys = _override_keys_for(
        overrides=overrides or {}, cadence=cadence, period_key=period_key
    )
    if override_keys:
        for k in override_keys:
            q = by_key.get(str(k))
            if q:
                order.append(q)

    seen = {str(q.id) for q in order}
    seed = _seed(cadence=cadence, period_key=period_key, ruleset_version=ruleset)
    remaining = [q for q in active if str(q.id) not in seen]
    remaining.sort(key=lambda q: _hash_choice(seed=seed, key=str(q.key)))

    out = order + remaining
    return out[: max(0, int(limit))]


def ensure_assignments(
    session: Session,
    *,
    user_id: str,
    period_key: str,
    quests: list[Quest],
    now: datetime | None = None,
) -> list[QuestAssignment]:
    now_dt = _as_aware_utc(now) or datetime.now(UTC)
    unique_quests: list[Quest] = []
    seen: set[str] = set()
    for q in quests:
        qid = str(getattr(q, "id", "") or "")
        if not qid or qid in seen:
            continue
        seen.add(qid)
        unique_quests.append(q)

    quest_ids = [str(q.id) for q in unique_quests if q and q.id]
    if not quest_ids:
        return []

    def _query_existing() -> dict[str, QuestAssignment]:
        existing = session.scalars(
            select(QuestAssignment)
            .where(QuestAssignment.user_id == str(user_id))
            .where(QuestAssignment.period_key == str(period_key))
            .where(QuestAssignment.quest_id.in_(quest_ids))
        ).all()
        return {str(a.quest_id): a for a in existing}

    by_qid = _query_existing()
    missing = [qid for qid in quest_ids if qid not in by_qid]

    if missing:
        # Concurrency-safe idempotency: multiple requests for the same user/period can
        # race to create assignments. Use a SAVEPOINT and re-query on conflict.
        from sqlalchemy.exc import IntegrityError

        try:
            with session.begin_nested():
                for qid in missing:
                    session.add(
                        QuestAssignment(
                            id=f"qa_{uuid4().hex}",
                            quest_id=str(qid),
                            user_id=str(user_id),
                            period_key=str(period_key),
                            progress_count=0,
                            claimed_at=None,
                            created_at=now_dt,
                        )
                    )
                session.flush()
        except IntegrityError:
            pass

        by_qid = _query_existing()

    out: list[QuestAssignment] = []
    for q in unique_quests:
        a = by_qid.get(str(q.id))
        if a is not None:
            out.append(a)
    return out


def _payload_dict(ev: Event) -> dict[str, Any]:
    try:
        parsed = orjson.loads((ev.payload_json or "{}").encode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _matches_filters(*, quest: Quest, payload: dict[str, Any]) -> bool:
    raw = str(quest.filters_json or "").strip()
    if not raw or raw == "{}":
        return True
    try:
        filt = orjson.loads(raw.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return True
    if not isinstance(filt, dict) or not filt:
        return True

    def match_node(node: Any, cur: Any) -> bool:  # noqa: ANN401
        if isinstance(node, dict):
            ops = {"eq", "gte", "lte", "in"}
            if ops & set(node.keys()):
                val = cur
                if "eq" in node and val != node["eq"]:
                    return False
                if "gte" in node:
                    try:
                        if float(val) < float(node["gte"]):
                            return False
                    except Exception:  # noqa: BLE001
                        return False
                if "lte" in node:
                    try:
                        if float(val) > float(node["lte"]):
                            return False
                    except Exception:  # noqa: BLE001
                        return False
                if "in" in node:
                    opts = node["in"]
                    if isinstance(opts, list):
                        if val not in opts:
                            return False
                return True

            if not isinstance(cur, dict):
                return False
            for k, v in node.items():
                if k not in cur:
                    return False
                if not match_node(v, cur.get(k)):
                    return False
            return True

        return cur == node

    return match_node(filt, payload)


@dataclass(frozen=True)
class ApplyResult:
    applied: int
    daily_period_key: str
    weekly_period_key: str


def apply_event_to_quests(session: Session, *, event: Event) -> ApplyResult:
    if not event.user_id:
        return ApplyResult(applied=0, daily_period_key="", weekly_period_key="")

    now = _as_aware_utc(event.created_at) or datetime.now(UTC)
    kst_dt = now.astimezone(KST)
    daily_key = kst_dt.date().strftime("%Y-%m-%d")
    year, week, _ = kst_dt.date().isocalendar()
    weekly_key = f"{int(year)}W{int(week):02d}"

    overrides = load_quest_overrides()
    progressed: list[dict[str, Any]] = []

    def run_cadence(cadence: Cadence, period_key: str, limit: int) -> int:
        selected = select_quests_for_period(
            session,
            cadence=cadence,
            period_key=period_key,
            limit=limit,
            now=now,
            overrides=overrides,
        )
        if not selected:
            return 0
        assignments = ensure_assignments(
            session,
            user_id=str(event.user_id),
            period_key=period_key,
            quests=selected,
            now=now,
        )
        # Ensure pending assignments (and the event itself) are flushed so subsequent
        # apply calls in the same transaction don't violate the unique constraint.
        session.flush()
        by_qid = {str(q.id): q for q in selected}

        payload = _payload_dict(event)
        assignment_ids = [str(a.id) for a in assignments if a and a.id]
        applied_rows = (
            session.scalars(
                select(QuestEventApplied.assignment_id)
                .where(QuestEventApplied.event_id == str(event.id))
                .where(QuestEventApplied.assignment_id.in_(assignment_ids))
            ).all()
            if assignment_ids
            else []
        )
        already = {str(x) for x in applied_rows if x}

        applied = 0
        for a in assignments:
            q = by_qid.get(str(a.quest_id))
            if not q:
                continue
            if str(q.event_type or "") != str(event.type or ""):
                continue
            if a.claimed_at is not None:
                continue
            if str(a.id) in already:
                continue
            if not _matches_filters(quest=q, payload=payload):
                continue
            session.add(
                QuestEventApplied(
                    event_id=str(event.id),
                    assignment_id=str(a.id),
                    applied_at=now,
                )
            )
            a.progress_count = int(a.progress_count or 0) + 1
            goal = int(q.goal_count or 1)
            if goal > 0:
                a.progress_count = min(int(a.progress_count), goal)
            session.add(a)
            progressed.append(
                {
                    "cadence": str(cadence),
                    "period_key": str(period_key),
                    "quest_id": str(q.id),
                    "quest_key": str(q.key),
                    "assignment_id": str(a.id),
                    "progress_count": int(a.progress_count or 0),
                    "goal_count": int(q.goal_count or 1),
                }
            )
            applied += 1
        return applied

    applied = 0
    applied += run_cadence("daily", daily_key, 3)
    applied += run_cadence("weekly", weekly_key, 3)

    if applied > 0 and progressed:
        try:
            log_event(
                session,
                type="quest_progressed",
                user_id=str(event.user_id),
                request=None,
                payload={
                    "trigger_event_id": str(event.id),
                    "trigger_event_type": str(event.type),
                    "applied": int(applied),
                    "progressed": progressed[:12],
                    "daily_period_key": str(daily_key),
                    "weekly_period_key": str(weekly_key),
                },
                now=now,
            )
        except Exception:  # noqa: BLE001
            pass
    return ApplyResult(
        applied=applied, daily_period_key=daily_key, weekly_period_key=weekly_key
    )
