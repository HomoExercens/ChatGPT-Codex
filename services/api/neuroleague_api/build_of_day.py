from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import orjson
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.models import Blueprint, Match, ModerationHide
from neuroleague_api.storage_backend import get_storage_backend, guess_content_type

Mode = Literal["1v1", "team"]

KST = ZoneInfo("Asia/Seoul")

BOD_OVERRIDE_KEY = "ops/build_of_day_override.json"


def _as_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def kst_date_key(*, now_utc: datetime | None = None) -> str:
    now = _as_aware_utc(now_utc) or datetime.now(UTC)
    return now.astimezone(KST).date().strftime("%Y-%m-%d")


def load_build_of_day_overrides() -> dict[str, Any]:
    backend = get_storage_backend()
    if not backend.exists(key=BOD_OVERRIDE_KEY):
        return {}
    try:
        raw = backend.get_bytes(key=BOD_OVERRIDE_KEY)
        parsed = orjson.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def write_build_of_day_overrides(payload: dict[str, Any]) -> None:
    backend = get_storage_backend()
    backend.put_bytes(
        key=BOD_OVERRIDE_KEY,
        data=orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS),
        content_type=guess_content_type("build_of_day_override.json"),
    )


def _override_blueprint_id(
    *, overrides: dict[str, Any], date_key: str, mode: Mode
) -> str | None:
    raw_overrides = overrides.get("overrides")
    if not isinstance(raw_overrides, dict):
        return None
    day = raw_overrides.get(str(date_key))
    if not isinstance(day, dict):
        return None
    slot = day.get(str(mode))
    if isinstance(slot, str):
        return slot.strip() or None
    if isinstance(slot, dict):
        bid = slot.get("blueprint_id")
        return str(bid).strip() if isinstance(bid, str) and bid.strip() else None
    return None


def _is_valid_override_target(
    session: Session, *, blueprint_id: str, mode: Mode, ruleset_version: str
) -> bool:
    bp = session.get(Blueprint, blueprint_id)
    if not bp or bp.status != "submitted":
        return False
    if str(bp.mode) != str(mode):
        return False
    if str(bp.ruleset_version) != str(ruleset_version):
        return False
    if str(bp.user_id or "").startswith("bot_"):
        return False
    hidden = session.scalar(
        select(ModerationHide.target_id)
        .where(ModerationHide.target_type == "build")
        .where(ModerationHide.target_id == blueprint_id)
        .limit(1)
    )
    return hidden is None


def select_auto_build_of_day_blueprint_id(
    session: Session, *, date_key: str, mode: Mode, ruleset_version: str
) -> str | None:
    hidden_build_ids = session.scalars(
        select(ModerationHide.target_id).where(ModerationHide.target_type == "build")
    ).all()

    bps = session.scalars(
        select(Blueprint)
        .where(Blueprint.status == "submitted")
        .where(Blueprint.mode == str(mode))
        .where(Blueprint.ruleset_version == str(ruleset_version))
        .where(~Blueprint.user_id.like("bot_%"))
        .order_by(
            desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id.asc()
        )
        .limit(500)
    ).all()

    latest_by_user: dict[str, Blueprint] = {}
    for bp in bps:
        if hidden_build_ids and bp.id in hidden_build_ids:
            continue
        if bp.user_id in latest_by_user:
            continue
        latest_by_user[bp.user_id] = bp

    candidate_ids = [b.id for b in latest_by_user.values()]
    if not candidate_ids:
        return None

    matches = session.scalars(
        select(Match)
        .where(Match.status == "done")
        .where(Match.mode == str(mode))
        .where(Match.ruleset_version == str(ruleset_version))
        .where(
            (Match.blueprint_a_id.in_(candidate_ids))
            | (Match.blueprint_b_id.in_(candidate_ids))
        )
        .order_by(desc(Match.finished_at), desc(Match.created_at), Match.id.asc())
    ).all()

    stats: dict[str, dict[str, int]] = {
        bid: {"matches": 0, "wins": 0, "draws": 0} for bid in candidate_ids
    }
    for m in matches:
        if m.blueprint_a_id in stats:
            s = stats[m.blueprint_a_id]
            s["matches"] += 1
            if m.result == "A":
                s["wins"] += 1
            elif m.result not in ("A", "B"):
                s["draws"] += 1
        if m.blueprint_b_id in stats:
            s = stats[m.blueprint_b_id]
            s["matches"] += 1
            if m.result == "B":
                s["wins"] += 1
            elif m.result not in ("A", "B"):
                s["draws"] += 1

    eligible: list[tuple[str, float, int]] = []
    for bid, s in stats.items():
        matches_n = int(s.get("matches") or 0)
        if matches_n < 5:
            continue
        wins = int(s.get("wins") or 0)
        draws = int(s.get("draws") or 0)
        winrate = (wins + 0.5 * draws) / matches_n
        eligible.append((bid, float(winrate), matches_n))

    if not eligible:
        return None

    eligible.sort(key=lambda t: (-t[1], -t[2], t[0]))
    pool = eligible[: min(10, len(eligible))]

    msg = f"{ruleset_version}:{mode}:{date_key}"
    digest = hashlib.sha256(msg.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:8], "little", signed=False) % len(pool)
    return pool[idx][0]


@dataclass(frozen=True)
class BuildOfDayResolved:
    date_key: str
    mode: Mode
    source: Literal["override", "auto", "none"]
    picked_blueprint_id: str | None
    override_blueprint_id: str | None
    auto_blueprint_id: str | None


def resolve_build_of_day(
    session: Session,
    *,
    date_key: str,
    mode: Mode,
    ruleset_version: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> BuildOfDayResolved:
    settings = Settings()
    ruleset = str(ruleset_version or settings.ruleset_version)
    overrides = overrides or load_build_of_day_overrides()

    override_id = _override_blueprint_id(
        overrides=overrides, date_key=date_key, mode=mode
    )
    override_ok = (
        _is_valid_override_target(
            session, blueprint_id=override_id, mode=mode, ruleset_version=ruleset
        )
        if override_id
        else False
    )

    auto_id = select_auto_build_of_day_blueprint_id(
        session, date_key=date_key, mode=mode, ruleset_version=ruleset
    )

    if override_id and override_ok:
        return BuildOfDayResolved(
            date_key=date_key,
            mode=mode,
            source="override",
            picked_blueprint_id=override_id,
            override_blueprint_id=override_id,
            auto_blueprint_id=auto_id,
        )
    if auto_id:
        return BuildOfDayResolved(
            date_key=date_key,
            mode=mode,
            source="auto",
            picked_blueprint_id=auto_id,
            override_blueprint_id=override_id,
            auto_blueprint_id=auto_id,
        )
    return BuildOfDayResolved(
        date_key=date_key,
        mode=mode,
        source="none",
        picked_blueprint_id=None,
        override_blueprint_id=override_id,
        auto_blueprint_id=None,
    )
