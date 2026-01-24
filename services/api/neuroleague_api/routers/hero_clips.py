from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import orjson

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import DBSession
from neuroleague_api.hero_clips import (
    ensure_hero_override_exists,
    load_hero_override,
    recompute_hero_clips,
)
from neuroleague_api.storage_backend import get_storage_backend, guess_content_type


def _require_admin(x_admin_token: str | None) -> None:
    settings = Settings()
    expected = str(settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=401, detail="admin_disabled")
    if str(x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class HeroClipsRecomputeOut(BaseModel):
    ok: bool = True
    generated_at: str
    ruleset_version: str
    window_days: int
    by_mode: dict[str, list[str]] = Field(default_factory=dict)
    keys: dict[str, str] = Field(default_factory=dict)
    candidate_count: int = 0


router = APIRouter(prefix="/api/ops/hero_clips", tags=["ops"])


@router.post("/recompute", response_model=HeroClipsRecomputeOut)
def recompute(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> HeroClipsRecomputeOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)
    res = recompute_hero_clips(db, now=now)
    return HeroClipsRecomputeOut(
        ok=bool(res.get("ok", True)),
        generated_at=str(res.get("generated_at") or now.isoformat()),
        ruleset_version=str(res.get("ruleset_version") or Settings().ruleset_version),
        window_days=int(res.get("window_days") or 14),
        by_mode=res.get("by_mode") or {},
        keys=res.get("keys") or {},
        candidate_count=int(res.get("candidate_count") or 0),
    )


class HeroClipsCandidatesOut(BaseModel):
    generated_at: str | None = None
    ruleset_version: str | None = None
    window_days: int | None = None
    requested_range: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    by_mode: dict[str, Any] = Field(default_factory=dict)
    keys: dict[str, str] = Field(default_factory=dict)


class HeroOverrideOut(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    storage_key: str = "ops/hero_clips.override.json"


class HeroOverrideUpdateIn(BaseModel):
    mode: Literal["1v1", "team"]
    op: Literal["pin", "unpin", "exclude", "unexclude"]
    replay_id: str | None = Field(default=None, max_length=80)
    replay_ids: list[str] = Field(default_factory=list)


@router.get("/candidates", response_model=HeroClipsCandidatesOut)
def candidates(
    range: str | None = None,  # noqa: A002
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> HeroClipsCandidatesOut:
    _require_admin(x_admin_token)
    backend = get_storage_backend()
    now = datetime.now(UTC)
    ensure_hero_override_exists(backend=backend, now=now)
    override = load_hero_override(backend=backend)

    auto: dict[str, Any] = {}
    if backend.exists(key="ops/hero_clips.auto.json"):
        try:
            raw = backend.get_bytes(key="ops/hero_clips.auto.json")
            parsed = orjson.loads(raw)
            auto = parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001
            auto = {}

    by_mode_out: dict[str, Any] = {}
    for mode in ("1v1", "team"):
        pinned: list[str] = []
        excluded: list[str] = []
        bm = override.get("by_mode")
        if isinstance(bm, dict) and isinstance(bm.get(mode), dict):
            entry = bm.get(mode) or {}
            pinned = [str(x) for x in (entry.get("pin") or []) if str(x)]
            excluded = [str(x) for x in (entry.get("exclude") or []) if str(x)]

        cur: dict[str, Any] = {}
        bm_auto = auto.get("by_mode")
        if isinstance(bm_auto, dict) and isinstance(bm_auto.get(mode), dict):
            cur = bm_auto.get(mode) or {}
        items = cur.get("items") if isinstance(cur, dict) else None
        selected = cur.get("selected") if isinstance(cur, dict) else None
        items_out = items if isinstance(items, list) else []
        selected_out = selected if isinstance(selected, list) else []

        by_mode_out[mode] = {
            "pinned": pinned,
            "excluded": excluded,
            "selected": selected_out,
            "items": items_out[:50],
        }

    return HeroClipsCandidatesOut(
        generated_at=str(auto.get("generated_at") or "") or None,
        ruleset_version=str(auto.get("ruleset_version") or "") or None,
        window_days=int(auto.get("window_days") or 0) or None,
        requested_range=range,
        config=override.get("config") if isinstance(override.get("config"), dict) else {},
        by_mode=by_mode_out,
        keys={
            "auto": "ops/hero_clips.auto.json",
            "override": "ops/hero_clips.override.json",
        },
    )


@router.get("/override", response_model=HeroOverrideOut)
def get_override(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> HeroOverrideOut:
    _require_admin(x_admin_token)
    backend = get_storage_backend()
    ensure_hero_override_exists(backend=backend, now=datetime.now(UTC))
    data = load_hero_override(backend=backend)
    return HeroOverrideOut(data=data)


@router.post("/override", response_model=HeroOverrideOut)
def update_override(
    payload: HeroOverrideUpdateIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> HeroOverrideOut:
    _require_admin(x_admin_token)
    backend = get_storage_backend()
    now = datetime.now(UTC)
    ensure_hero_override_exists(backend=backend, now=now)
    data = load_hero_override(backend=backend)
    if not isinstance(data, dict):
        data = {}

    data.setdefault("version", 2)
    data["updated_at"] = now.isoformat()
    by_mode = data.get("by_mode")
    if not isinstance(by_mode, dict):
        by_mode = {}
        data["by_mode"] = by_mode
    for m in ("1v1", "team"):
        entry = by_mode.get(m)
        if not isinstance(entry, dict):
            entry = {"pin": [], "exclude": []}
            by_mode[m] = entry
        entry.setdefault("pin", [])
        entry.setdefault("exclude", [])

    entry = by_mode.get(payload.mode) or {}
    pin: list[str] = [str(x) for x in (entry.get("pin") or []) if str(x)]
    exc: list[str] = [str(x) for x in (entry.get("exclude") or []) if str(x)]

    ids = [str(payload.replay_id or "").strip()] if payload.replay_id else []
    ids.extend([str(x or "").strip() for x in (payload.replay_ids or [])])
    ids = [x for x in ids if x]

    def _add_front(lst: list[str], rid: str) -> None:
        if rid in lst:
            lst.remove(rid)
        lst.insert(0, rid)

    for rid in ids:
        if payload.op == "pin":
            if rid in exc:
                exc.remove(rid)
            _add_front(pin, rid)
        elif payload.op == "unpin":
            if rid in pin:
                pin.remove(rid)
        elif payload.op == "exclude":
            if rid in pin:
                pin.remove(rid)
            _add_front(exc, rid)
        else:  # unexclude
            if rid in exc:
                exc.remove(rid)

    entry["pin"] = pin[:50]
    entry["exclude"] = exc[:200]
    by_mode[payload.mode] = entry

    backend.put_bytes(
        key="ops/hero_clips.override.json",
        data=orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS),
        content_type=guess_content_type("hero_clips.override.json"),
    )
    return HeroOverrideOut(data=data)
