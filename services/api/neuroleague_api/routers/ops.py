from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

import orjson

from neuroleague_api.balance_report import compute_balance_report
from neuroleague_api.build_of_day import (
    BOD_OVERRIDE_KEY,
    KST,
    load_build_of_day_overrides,
    resolve_build_of_day,
    write_build_of_day_overrides,
)
from neuroleague_api.core.config import Settings
from neuroleague_api.deps import DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.growth_metrics import (
    FUNNEL_CLIPS_V1,
    FUNNEL_GROWTH_V1,
    FUNNEL_SHARE_V1,
    load_experiment_stats,
    load_funnel_daily_series,
    load_funnel_summary,
    load_metrics_series,
    load_shorts_variants,
    rollup_growth_metrics,
)
from neuroleague_api.metrics import recent_http_errors_db
from neuroleague_api.models import (
    AlertSent,
    Blueprint,
    DiscordOutbox,
    Event,
    Match,
    ModerationHide,
    RenderJob,
    Replay,
    Report,
    User,
    UserSoftBan,
)
from neuroleague_api.storage_backend import get_storage_backend

router = APIRouter(prefix="/api/ops", tags=["ops"])


def _is_e2e_fast() -> bool:
    raw = str(os.environ.get("NEUROLEAGUE_E2E_FAST", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _probe_ray_nodes(*, timeout_sec: float = 2.0) -> tuple[bool, int, str | None]:
    """
    Run Ray connectivity checks in a subprocess to avoid crashing the API process
    when Ray's GCS is unhealthy.
    """
    code = r"""
import json
import os

try:
    import ray  # type: ignore
except Exception as exc:
    print(json.dumps({"ok": False, "nodes": 0, "error": f"import_error:{exc}"}))
    raise SystemExit(0)

addr = (os.environ.get("NEUROLEAGUE_RAY_ADDRESS") or "").strip()
try:
    if addr:
        ray.init(address=addr, ignore_reinit_error=True, log_to_driver=False)
    else:
        ray.init(address="auto", ignore_reinit_error=True, log_to_driver=False)
    nodes = ray.nodes()
    alive = len([n for n in nodes if n.get("Alive")])
    print(json.dumps({"ok": alive > 0, "nodes": alive, "error": None}))
except Exception as exc:
    print(json.dumps({"ok": False, "nodes": 0, "error": str(exc)[:240]}))
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=float(timeout_sec),
            text=True,
        )
        out = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
        try:
            parsed = orjson.loads(out.encode("utf-8")) if out else {}
            ok = bool(parsed.get("ok")) if isinstance(parsed, dict) else False
            nodes = int(parsed.get("nodes") or 0) if isinstance(parsed, dict) else 0
            err = (
                str(parsed.get("error") or "")[:240] if isinstance(parsed, dict) else None
            )
            return ok, nodes, (err or None)
        except Exception:  # noqa: BLE001
            return False, 0, "parse_error"
    except subprocess.TimeoutExpired:
        return False, 0, "timeout"


def _require_admin(x_admin_token: str | None) -> None:
    settings = Settings()
    expected = str(settings.admin_token or "").strip()
    if not expected:
        raise HTTPException(status_code=401, detail="admin_disabled")
    if str(x_admin_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class OpsStatusOut(BaseModel):
    timestamp: str
    ruleset_version: str
    pack_hash: str | None = None
    db: dict[str, Any] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    ray: dict[str, Any] = Field(default_factory=dict)
    worker_ok: bool = False
    render_jobs: dict[str, Any] = Field(default_factory=dict)
    pending_jobs_count: int = 0
    reports_pending: int = 0
    scheduler: dict[str, Any] = Field(default_factory=dict)
    last_rollup_at: str | None = None
    last_balance_report_at: str | None = None
    last_backup_at: str | None = None
    last_backup_key: str | None = None
    discord_last_post_at: str | None = None
    discord_last_error: str | None = None


@router.get("/status", response_model=OpsStatusOut)
def status(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsStatusOut:
    _require_admin(x_admin_token)
    settings = Settings()
    now = datetime.now(UTC)

    pack_hash: str | None = None
    try:
        from neuroleague_sim.pack_loader import active_pack_hash

        pack_hash = active_pack_hash()
    except Exception:  # noqa: BLE001
        pack_hash = None

    db_ok = False
    db_err: str | None = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_err = str(exc)[:400]

    storage_ok = False
    storage_err: str | None = None
    storage_kind = str(settings.storage_backend or "local")
    try:
        backend = get_storage_backend()
        # For S3, a HEAD request via exists() is the cheapest connectivity check we have.
        _ = backend.exists(key="ops/ready.txt")
        storage_ok = True
    except Exception as exc:  # noqa: BLE001
        storage_ok = False
        storage_err = str(exc)[:400]

    ray_ok = False
    ray_nodes = 0
    ray_err: str | None = None
    if _is_e2e_fast():
        # FAST mode treats heavy work as sync-safe; don't hard-require Ray to be healthy here.
        ray_ok = False
        ray_nodes = 0
        ray_err = "skipped_e2e_fast"
    else:
        if settings.ray_address or os.environ.get("RAY_ADDRESS"):
            ray_ok, ray_nodes, ray_err = _probe_ray_nodes(timeout_sec=2.0)
        else:
            # Local dev: Ray may not be initialized until the first background job runs.
            ray_ok, ray_nodes, ray_err = _probe_ray_nodes(timeout_sec=2.0)

    queued = int(
        db.scalar(select(func.count(RenderJob.id)).where(RenderJob.status == "queued"))
        or 0
    )
    running = int(
        db.scalar(select(func.count(RenderJob.id)).where(RenderJob.status == "running"))
        or 0
    )
    pending_jobs = int(queued + running)

    reports_pending = int(
        db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
    )

    last_rollup = db.scalar(
        select(Event.created_at)
        .where(Event.type == "ops_metrics_rollup")
        .order_by(desc(Event.created_at))
        .limit(1)
    )
    last_balance = db.scalar(
        select(Event.created_at)
        .where(Event.type == "ops_balance_report")
        .order_by(desc(Event.created_at))
        .limit(1)
    )

    last_backup_at: str | None = None
    last_backup_key: str | None = None
    try:
        backend = get_storage_backend()
        if backend.exists(key="ops/last_backup.json"):
            raw = backend.get_bytes(key="ops/last_backup.json")
            parsed = orjson.loads(raw)
            if isinstance(parsed, dict):
                ts = parsed.get("timestamp")
                key = parsed.get("backup_key")
                if isinstance(ts, str):
                    last_backup_at = ts
                if isinstance(key, str):
                    last_backup_key = key
    except Exception:  # noqa: BLE001
        last_backup_at = None
        last_backup_key = None

    discord_last_post = db.scalar(
        select(DiscordOutbox.sent_at)
        .where(DiscordOutbox.status == "sent")
        .order_by(desc(DiscordOutbox.sent_at))
        .limit(1)
    )
    discord_last_err = db.scalar(
        select(DiscordOutbox.last_error)
        .where(DiscordOutbox.last_error.is_not(None))
        .order_by(desc(DiscordOutbox.created_at))
        .limit(1)
    )

    return OpsStatusOut(
        timestamp=now.isoformat(),
        ruleset_version=settings.ruleset_version,
        pack_hash=pack_hash,
        db={"ok": db_ok, "error": db_err},
        storage={"ok": storage_ok, "error": storage_err, "backend": storage_kind},
        ray={
            "ok": ray_ok,
            "error": ray_err,
            "configured": bool(settings.ray_address),
            "nodes": ray_nodes,
        },
        worker_ok=bool(_is_e2e_fast() or (ray_ok and ray_nodes > 0)),
        render_jobs={"queued": queued, "running": running},
        pending_jobs_count=pending_jobs,
        reports_pending=reports_pending,
        scheduler={
            "enabled": bool(getattr(settings, "scheduler_enabled", False)),
            "interval_minutes": int(
                getattr(settings, "scheduler_interval_minutes", 0) or 0
            ),
        },
        last_rollup_at=last_rollup.isoformat() if last_rollup else None,
        last_balance_report_at=last_balance.isoformat() if last_balance else None,
        last_backup_at=last_backup_at,
        last_backup_key=last_backup_key,
        discord_last_post_at=discord_last_post.isoformat()
        if discord_last_post
        else None,
        discord_last_error=str(discord_last_err)[:400] if discord_last_err else None,
    )


class OpsWeeklyOut(BaseModel):
    week_id: str
    theme: dict[str, Any] = Field(default_factory=dict)
    override: dict[str, Any] | None = None
    override_active: bool = False
    storage_key: str = "ops/weekly_theme_override.json"


class OpsWeeklyOverrideIn(BaseModel):
    clear: bool = False
    week_id: str | None = None
    name: str | None = None
    description: str | None = None
    featured_portal_ids: list[str] = Field(default_factory=list)
    featured_augment_ids: list[str] = Field(default_factory=list)
    tournament_rules: dict[str, Any] = Field(default_factory=dict)


def _iso_week_id(dt: datetime) -> str:
    year, week, _weekday = dt.isocalendar()
    return f"{int(year)}W{int(week):02d}"


def _load_weekly_override(*, week_id: str) -> tuple[dict[str, Any] | None, bool]:
    backend = get_storage_backend()
    key = "ops/weekly_theme_override.json"
    if not backend.exists(key=key):
        return None, False
    try:
        raw = backend.get_bytes(key=key)
        parsed = orjson.loads(raw)
        if not isinstance(parsed, dict) or not parsed:
            return None, False
        active = str(parsed.get("week_id") or "") == str(week_id)
        return parsed, active
    except Exception:  # noqa: BLE001
        return None, False


@router.get("/weekly", response_model=OpsWeeklyOut)
def weekly_ops(
    week_id: str | None = None,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsWeeklyOut:
    _require_admin(x_admin_token)
    wid = str(week_id or "").strip() or _iso_week_id(datetime.now(UTC))
    override, active = _load_weekly_override(week_id=wid)
    from neuroleague_api.routers.meta import weekly as weekly_theme

    theme = weekly_theme(week_id=wid)
    return OpsWeeklyOut(
        week_id=wid, theme=theme, override=override, override_active=active
    )


@router.post("/weekly/override", response_model=OpsWeeklyOut)
def weekly_override(
    request: Request,
    payload: OpsWeeklyOverrideIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsWeeklyOut:
    _require_admin(x_admin_token)
    backend = get_storage_backend()
    key = "ops/weekly_theme_override.json"
    now = datetime.now(UTC)

    if bool(payload.clear):
        backend.put_bytes(
            key=key,
            data=orjson.dumps({}, option=orjson.OPT_SORT_KEYS),
            content_type="application/json",
        )
        try:
            log_event(
                db,
                type="ops_weekly_override",
                user_id=None,
                request=request,
                payload={"action": "clear"},
                now=now,
            )
            db.commit()
        except Exception:  # noqa: BLE001
            pass

        wid = str(payload.week_id or "").strip() or _iso_week_id(now)
        from neuroleague_api.routers.meta import weekly as weekly_theme

        theme = weekly_theme(week_id=wid)
        return OpsWeeklyOut(
            week_id=wid, theme=theme, override=None, override_active=False
        )

    wid = str(payload.week_id or "").strip()
    if not wid:
        raise HTTPException(status_code=400, detail={"error": "week_id_required"})

    from neuroleague_sim.modifiers import AUGMENTS, PORTALS

    portal_ids = [
        str(x).strip() for x in (payload.featured_portal_ids or []) if str(x).strip()
    ]
    portal_ids = sorted(set(portal_ids))
    if not portal_ids:
        raise HTTPException(
            status_code=400, detail={"error": "featured_portal_ids_required"}
        )
    invalid_portals = [p for p in portal_ids if p not in PORTALS]
    if invalid_portals:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_portal_ids", "ids": invalid_portals},
        )

    augment_ids = [
        str(x).strip() for x in (payload.featured_augment_ids or []) if str(x).strip()
    ]
    augment_ids = sorted(set(augment_ids))
    invalid_augments = [a for a in augment_ids if a not in AUGMENTS]
    if invalid_augments:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_augment_ids", "ids": invalid_augments},
        )

    out = {
        "week_id": wid,
        "name": str(payload.name)
        if payload.name is not None
        else f"Weekly Theme {wid}",
        "description": str(payload.description or ""),
        "featured_portal_ids": portal_ids,
        "featured_augment_ids": augment_ids,
        "tournament_rules": payload.tournament_rules or {},
        "updated_at": now.isoformat(),
    }

    backend.put_bytes(
        key=key,
        data=orjson.dumps(out, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )
    try:
        log_event(
            db,
            type="ops_weekly_override",
            user_id=None,
            request=request,
            payload={
                "action": "set",
                "week_id": wid,
                "featured_portals": portal_ids,
                "featured_augments": augment_ids,
            },
            now=now,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    override, active = _load_weekly_override(week_id=wid)
    from neuroleague_api.routers.meta import weekly as weekly_theme

    theme = weekly_theme(week_id=wid)
    return OpsWeeklyOut(
        week_id=wid, theme=theme, override=override, override_active=active
    )


class PackEntry(BaseModel):
    path: str
    ruleset_version: str | None = None
    pack_hash: str | None = None
    declared_pack_hash: str | None = None
    created_at: str | None = None
    valid: bool = True


class OpsPacksOut(BaseModel):
    active_ruleset_version: str
    active_pack_hash: str | None = None
    active_pack_path: str | None = None
    available_packs: list[PackEntry] = Field(default_factory=list)
    candidate: PackEntry | None = None
    promotion: dict[str, Any] | None = None
    storage_keys: dict[str, str] = Field(default_factory=dict)


class OpsPackCandidateIn(BaseModel):
    path: str


class OpsPackPromoteIn(BaseModel):
    scheduled_for: str | None = None
    note: str | None = None


def _repo_root_api() -> Path:
    # services/api/neuroleague_api/routers -> repo root is 4 levels up
    return Path(__file__).resolve().parents[4]


def _relpath(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:  # noqa: BLE001
        return str(path)


def _load_optional_json_dict(*, backend, key: str) -> dict[str, Any] | None:
    if not backend.exists(key=key):
        return None
    try:
        raw = backend.get_bytes(key=key)
        parsed = orjson.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # noqa: BLE001
        return None
    return None


def _load_optional_json(*, backend, key: str) -> Any | None:
    if not backend.exists(key=key):
        return None
    try:
        raw = backend.get_bytes(key=key)
        return orjson.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _packs_snapshot() -> OpsPacksOut:
    settings = Settings()
    active_ruleset = (
        str(os.environ.get("NEUROLEAGUE_ACTIVE_RULESET_VERSION") or "").strip()
        or str(os.environ.get("ACTIVE_RULESET_VERSION") or "").strip()
        or str(settings.ruleset_version)
    )

    repo_root = _repo_root_api()
    packs_root = (repo_root / "packs").resolve()

    from neuroleague_sim.pack_loader import (
        active_pack_hash,
        active_pack_path,
        compute_pack_hash,
        load_pack,
    )

    active_hash = active_pack_hash()
    active_path = active_pack_path()
    if active_path:
        try:
            active_path = _relpath(repo_root, Path(active_path))
        except Exception:  # noqa: BLE001
            pass

    available: list[PackEntry] = []
    if packs_root.exists():
        for p in sorted(packs_root.rglob("pack.json")):
            try:
                obj = load_pack(p)
                computed = compute_pack_hash(obj)
                declared = str(obj.get("pack_hash") or "").strip() or None
                valid = (declared is None) or (declared == computed)
                available.append(
                    PackEntry(
                        path=_relpath(repo_root, p),
                        ruleset_version=str(obj.get("ruleset_version") or "").strip()
                        or None,
                        pack_hash=computed,
                        declared_pack_hash=declared,
                        created_at=str(obj.get("created_at") or "").strip() or None,
                        valid=bool(valid),
                    )
                )
            except Exception:  # noqa: BLE001
                continue

    backend = get_storage_backend()
    candidate_key = "ops/pack_candidate.json"
    promotion_key = "ops/pack_promotion_latest.json"

    candidate_obj = _load_optional_json_dict(backend=backend, key=candidate_key)
    candidate = None
    if candidate_obj:
        candidate = PackEntry(
            path=str(candidate_obj.get("path") or ""),
            ruleset_version=str(candidate_obj.get("ruleset_version") or "").strip()
            or None,
            pack_hash=str(candidate_obj.get("pack_hash") or "").strip() or None,
            declared_pack_hash=None,
            created_at=str(candidate_obj.get("created_at") or "").strip() or None,
            valid=True,
        )

    promotion_obj = _load_optional_json_dict(backend=backend, key=promotion_key)

    return OpsPacksOut(
        active_ruleset_version=active_ruleset,
        active_pack_hash=active_hash,
        active_pack_path=active_path,
        available_packs=sorted(available, key=lambda r: r.path),
        candidate=candidate,
        promotion=promotion_obj,
        storage_keys={
            "candidate": candidate_key,
            "promotion_latest": promotion_key,
            "patch_notes": "ops/patch_notes.json",
        },
    )


@router.get("/packs", response_model=OpsPacksOut)
def packs_ops(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> OpsPacksOut:
    _require_admin(x_admin_token)
    return _packs_snapshot()


@router.post("/packs/candidate", response_model=OpsPacksOut)
def packs_set_candidate(
    request: Request,
    payload: OpsPackCandidateIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsPacksOut:
    _require_admin(x_admin_token)
    raw = str(payload.path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail={"error": "path_required"})

    repo_root = _repo_root_api()
    packs_root = (repo_root / "packs").resolve()
    p = (repo_root / raw).resolve()
    if packs_root != p and packs_root not in p.parents:
        raise HTTPException(
            status_code=400, detail={"error": "path_must_be_under_packs"}
        )
    if not p.exists() or p.name != "pack.json":
        raise HTTPException(status_code=400, detail={"error": "pack_not_found"})

    from neuroleague_sim.pack_loader import compute_pack_hash, load_pack

    pack = load_pack(p)
    computed = compute_pack_hash(pack)
    declared = str(pack.get("pack_hash") or "").strip() or None
    if declared and declared != computed:
        raise HTTPException(status_code=400, detail={"error": "pack_hash_mismatch"})

    now = datetime.now(UTC)
    record = {
        "path": _relpath(repo_root, p),
        "ruleset_version": str(pack.get("ruleset_version") or "").strip() or None,
        "pack_hash": computed,
        "created_at": str(pack.get("created_at") or "").strip() or None,
        "set_at": now.isoformat(),
    }

    backend = get_storage_backend()
    backend.put_bytes(
        key="ops/pack_candidate.json",
        data=orjson.dumps(record, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )

    try:
        log_event(
            db,
            type="ops_pack_candidate_set",
            user_id=None,
            request=request,
            payload=record,
            now=now,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    return _packs_snapshot()


@router.post("/packs/promote", response_model=OpsPacksOut)
def packs_promote_candidate(
    request: Request,
    payload: OpsPackPromoteIn,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsPacksOut:
    _require_admin(x_admin_token)
    backend = get_storage_backend()
    now = datetime.now(UTC)

    candidate = _load_optional_json_dict(backend=backend, key="ops/pack_candidate.json")
    if not candidate:
        raise HTTPException(status_code=400, detail={"error": "candidate_missing"})

    ts = now.strftime("%Y%m%d_%H%M%S")
    plan = {
        "approved_at": now.isoformat(),
        "scheduled_for": str(payload.scheduled_for).strip()
        if payload.scheduled_for
        else None,
        "note": str(payload.note).strip() if payload.note else None,
        "candidate": candidate,
        "instructions": [
            "Set NEUROLEAGUE_ACTIVE_RULESET_VERSION to candidate.ruleset_version (or ACTIVE_RULESET_VERSION).",
            "Deploy a build that contains the candidate pack.json at packs/<ruleset_version>/pack.json (or packs/<ruleset_version>/v1/pack.json).",
            "Restart API/worker/scheduler.",
        ],
    }
    backend.put_bytes(
        key=f"ops/pack_promotion_{ts}.json",
        data=orjson.dumps(plan, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )
    backend.put_bytes(
        key="ops/pack_promotion_latest.json",
        data=orjson.dumps(plan, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )

    # Append patch notes so /api/meta/season reflects ops actions (placeholder quality is ok).
    pn_key = "ops/patch_notes.json"
    existing = _load_optional_json(backend=backend, key=pn_key)
    if isinstance(existing, dict) and isinstance(existing.get("notes"), list):
        notes = [n for n in existing["notes"] if isinstance(n, dict)]
    elif isinstance(existing, list):
        notes = [n for n in existing if isinstance(n, dict)]
    else:
        notes = []

    entry = {
        "version": str(candidate.get("ruleset_version") or "candidate"),
        "date": now.date().isoformat(),
        "title": "Pack promotion approved",
        "pack_hash": str(candidate.get("pack_hash") or ""),
    }
    if not any(
        isinstance(n, dict)
        and str(n.get("title")) == str(entry.get("title"))
        and str(n.get("pack_hash") or "") == str(entry.get("pack_hash") or "")
        for n in notes
    ):
        notes.append(entry)
    backend.put_bytes(
        key=pn_key,
        data=orjson.dumps({"notes": notes}, option=orjson.OPT_SORT_KEYS),
        content_type="application/json",
    )

    try:
        log_event(
            db,
            type="ops_pack_promote",
            user_id=None,
            request=request,
            payload=plan,
            now=now,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    return _packs_snapshot()


@router.get("/balance/latest")
def balance_latest(
    mode: Literal["1v1", "team"] | None = None,
    queue_type: Literal["ranked", "tournament"] = "ranked",
    db: Session = DBSession,
) -> dict[str, Any]:
    settings = Settings()
    report = compute_balance_report(
        db,
        ruleset_version=settings.ruleset_version,
        queue_type=queue_type,
        limit_matches=10_000,
    )
    if mode is None:
        return report
    data = (report.get("modes") or {}).get(mode) or {
        "matches_total": 0,
        "overall": {
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "winrate": 0.0,
            "avg_elo_delta": 0.0,
        },
        "portals": [],
        "augments": [],
        "creatures": [],
        "items": [],
        "sigils": [],
        "synergies": [],
        "synergy_pairs": [],
    }
    return {
        "generated_at": report.get("generated_at"),
        "ruleset_version": report.get("ruleset_version"),
        "queue_type": report.get("queue_type"),
        "low_confidence_min_samples": report.get("low_confidence_min_samples"),
        "mode": mode,
        "data": data,
    }


class OpsReportOut(BaseModel):
    id: str
    reporter_user_id: str | None = None
    reporter_display_name: str | None = None
    target_user_id: str | None = None
    target_display_name: str | None = None
    target_type: str
    target_id: str
    reason: str
    status: str
    created_at: str
    resolved_at: str | None = None


class OpsReportsListOut(BaseModel):
    items: list[OpsReportOut]


@router.get("/reports", response_model=OpsReportsListOut)
def reports_list(
    limit: int = 50,
    status: Literal["open", "resolved", "all"] = "all",
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsReportsListOut:
    _require_admin(x_admin_token)
    q = select(Report).order_by(desc(Report.created_at)).limit(int(limit))
    if status != "all":
        q = q.where(Report.status == status)
    rows = db.scalars(q).all()
    reporter_ids = sorted({r.reporter_user_id for r in rows if r.reporter_user_id})
    reporters = (
        db.scalars(select(User).where(User.id.in_(reporter_ids))).all()
        if reporter_ids
        else []
    )
    reporter_by_id = {u.id: u for u in reporters}

    # Resolve target "author" user_id where possible (best-effort).
    clip_replay_ids = sorted({r.target_id for r in rows if r.target_type == "clip"})
    build_ids = sorted({r.target_id for r in rows if r.target_type == "build"})
    profile_ids = sorted({r.target_id for r in rows if r.target_type == "profile"})

    replay_by_id = (
        {
            r.id: r
            for r in db.scalars(
                select(Replay).where(Replay.id.in_(clip_replay_ids))
            ).all()
        }
        if clip_replay_ids
        else {}
    )
    match_ids = sorted(
        {replay_by_id[rid].match_id for rid in clip_replay_ids if rid in replay_by_id}
    )
    match_by_id = (
        {
            m.id: m
            for m in db.scalars(select(Match).where(Match.id.in_(match_ids))).all()
        }
        if match_ids
        else {}
    )
    bp_by_id = (
        {
            b.id: b
            for b in db.scalars(
                select(Blueprint).where(Blueprint.id.in_(build_ids))
            ).all()
        }
        if build_ids
        else {}
    )

    target_user_ids: set[str] = set()
    for rid in clip_replay_ids:
        replay = replay_by_id.get(rid)
        if replay:
            m = match_by_id.get(replay.match_id)
            if m and m.user_a_id:
                target_user_ids.add(str(m.user_a_id))
    for bid in build_ids:
        bp = bp_by_id.get(bid)
        if bp:
            target_user_ids.add(str(bp.user_id))
    for uid in profile_ids:
        target_user_ids.add(str(uid))

    target_users = (
        db.scalars(select(User).where(User.id.in_(sorted(target_user_ids)))).all()
        if target_user_ids
        else []
    )
    target_user_by_id = {u.id: u for u in target_users}

    def target_user_for_report(r: Report) -> tuple[str | None, str | None]:
        if r.target_type == "clip":
            replay = replay_by_id.get(r.target_id)
            if replay:
                m = match_by_id.get(replay.match_id)
                if m and m.user_a_id:
                    uid = str(m.user_a_id)
                    u = target_user_by_id.get(uid)
                    return uid, (u.display_name if u else None)
            return None, None
        if r.target_type == "build":
            bp = bp_by_id.get(r.target_id)
            if bp:
                uid = str(bp.user_id)
                u = target_user_by_id.get(uid)
                return uid, (u.display_name if u else None)
            return None, None
        if r.target_type == "profile":
            uid = str(r.target_id)
            u = target_user_by_id.get(uid)
            return uid, (u.display_name if u else None)
        return None, None

    return OpsReportsListOut(
        items=[
            OpsReportOut(
                id=r.id,
                reporter_user_id=r.reporter_user_id,
                reporter_display_name=reporter_by_id.get(
                    r.reporter_user_id
                ).display_name
                if r.reporter_user_id and reporter_by_id.get(r.reporter_user_id)
                else None,
                target_user_id=target_user_for_report(r)[0],
                target_display_name=target_user_for_report(r)[1],
                target_type=r.target_type,
                target_id=r.target_id,
                reason=r.reason,
                status=r.status,
                created_at=r.created_at.isoformat(),
                resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
            )
            for r in rows
        ]
    )


class OpsReportResolveOut(BaseModel):
    ok: bool = True
    report_id: str
    status: str
    resolved_at: str | None = None


@router.post("/reports/{report_id}/resolve", response_model=OpsReportResolveOut)
def report_resolve(
    report_id: str,
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsReportResolveOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)
    report = db.get(Report, str(report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = "resolved"
    report.resolved_at = now
    db.add(report)
    try:
        log_event(
            db,
            type="ops_report_resolve",
            user_id=None,
            request=request,
            payload={
                "report_id": str(report_id),
                "target_type": report.target_type,
                "target_id": report.target_id,
            },
            now=now,
        )
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return OpsReportResolveOut(
        report_id=report.id,
        status=report.status,
        resolved_at=report.resolved_at.isoformat(),
    )


class OpsHideTargetIn(BaseModel):
    target_type: Literal["clip", "build", "profile"]
    target_id: str = Field(min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=280)


class OpsHideTargetOut(BaseModel):
    ok: bool = True
    target_type: str
    target_id: str
    hidden_at: str


@router.post("/moderation/hide_target", response_model=OpsHideTargetOut)
def moderation_hide_target(
    req: OpsHideTargetIn,
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsHideTargetOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)

    existing = db.get(
        ModerationHide, {"target_type": req.target_type, "target_id": req.target_id}
    )
    if existing:
        existing.reason = (req.reason or existing.reason or "").strip()[
            :280
        ] or existing.reason
        existing.created_at = now
        db.add(existing)
    else:
        db.add(
            ModerationHide(
                target_type=req.target_type,
                target_id=req.target_id,
                reason=(req.reason or "").strip()[:280] or None,
                created_at=now,
            )
        )
    try:
        log_event(
            db,
            type="ops_moderation_hide",
            user_id=None,
            request=request,
            payload={
                "target_type": req.target_type,
                "target_id": req.target_id,
                "reason": req.reason,
            },
            now=now,
        )
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return OpsHideTargetOut(
        target_type=req.target_type, target_id=req.target_id, hidden_at=now.isoformat()
    )


class OpsSoftBanIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    duration_hours: int = Field(default=24, ge=1, le=24 * 30)
    reason: str | None = Field(default=None, max_length=280)


class OpsSoftBanOut(BaseModel):
    ok: bool = True
    user_id: str
    banned_until: str


@router.post("/moderation/soft_ban_user", response_model=OpsSoftBanOut)
def moderation_soft_ban_user(
    req: OpsSoftBanIn,
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsSoftBanOut:
    _require_admin(x_admin_token)
    now = datetime.now(UTC)
    user = db.get(User, str(req.user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    banned_until = now + timedelta(hours=int(req.duration_hours))
    existing = db.get(UserSoftBan, str(req.user_id))
    if existing:
        existing.banned_until = banned_until
        existing.reason = (req.reason or existing.reason or "").strip()[
            :280
        ] or existing.reason
        existing.created_at = now
        db.add(existing)
    else:
        db.add(
            UserSoftBan(
                user_id=str(req.user_id),
                banned_until=banned_until,
                reason=(req.reason or "").strip()[:280] or None,
                created_at=now,
            )
        )
    try:
        log_event(
            db,
            type="ops_soft_ban",
            user_id=None,
            request=request,
            payload={
                "user_id": str(req.user_id),
                "duration_hours": int(req.duration_hours),
                "reason": req.reason,
            },
            now=now,
        )
    except Exception:  # noqa: BLE001
        pass
    db.commit()
    return OpsSoftBanOut(
        user_id=str(req.user_id), banned_until=banned_until.isoformat()
    )


class MetricsDailyRow(BaseModel):
    date: str
    metrics: dict[str, float] = Field(default_factory=dict)


class MetricsSummaryOut(BaseModel):
    range: str
    from_date: str
    to_date: str
    kpis: dict[str, Any] = Field(default_factory=dict)
    daily: list[MetricsDailyRow] = Field(default_factory=list)


def _parse_days(range_raw: str | None) -> int:
    raw = str(range_raw or "7d").strip().lower()
    if raw.endswith("d"):
        raw = raw[:-1]
    try:
        days = int(raw)
    except Exception:  # noqa: BLE001
        return 7
    return max(1, min(365, days))


@router.get("/metrics/summary", response_model=MetricsSummaryOut)
def metrics_summary(
    range: str = "7d",
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> MetricsSummaryOut:
    _require_admin(x_admin_token)
    days = _parse_days(range)
    series = load_metrics_series(db, days=days)

    totals: dict[str, float] = {}
    last_vals: dict[str, float] = {}
    for row in series:
        for k, v in (row.get("metrics") or {}).items():
            totals[k] = float(totals.get(k, 0.0)) + float(v or 0.0)
            if float(v or 0.0) != 0.0:
                last_vals[k] = float(v or 0.0)

    share_open = float(totals.get("share_open_users", 0.0))
    guest_start = float(totals.get("guest_start_users", 0.0))
    first_match_done = float(totals.get("first_match_done_users", 0.0))
    replay_open = float(totals.get("replay_open_users", 0.0))
    forked = float(totals.get("blueprint_fork_users", 0.0))
    submitted = float(totals.get("blueprint_submit_users", 0.0))
    ranked_done = float(totals.get("ranked_done_users", 0.0))
    matches_total = float(totals.get("matches_total", 0.0))
    human_matches = float(totals.get("human_matches", 0.0))

    def rate(n: float, d: float) -> float:
        return float(n) / float(d) if d > 0 else 0.0

    kpis: dict[str, Any] = {
        "share_to_guest_start_rate": rate(guest_start, share_open),
        "guest_to_first_match_done_rate": rate(first_match_done, guest_start),
        "replay_open_rate": rate(replay_open, first_match_done),
        "remix_rate": rate(forked, replay_open),
        "submit_rate": rate(submitted, forked),
        "ranked_again_rate": rate(ranked_done, submitted),
        "human_match_rate": rate(human_matches, matches_total)
        if matches_total > 0
        else 0.0,
        "time_to_first_match_p50_sec": float(
            last_vals.get("time_to_first_match_p50_sec", 0.0)
        ),
        "time_to_first_match_p90_sec": float(
            last_vals.get("time_to_first_match_p90_sec", 0.0)
        ),
    }

    daily_rows = [
        MetricsDailyRow(date=str(r.get("date")), metrics=r.get("metrics") or {})
        for r in series
    ]
    from_date = (
        daily_rows[0].date if daily_rows else datetime.now(UTC).date().isoformat()
    )
    to_date = (
        daily_rows[-1].date if daily_rows else datetime.now(UTC).date().isoformat()
    )
    return MetricsSummaryOut(
        range=f"{days}d",
        from_date=from_date,
        to_date=to_date,
        kpis=kpis,
        daily=daily_rows,
    )


class FunnelStepOut(BaseModel):
    step: str
    users: int


class FunnelSummaryOut(BaseModel):
    funnel: str
    range: str
    steps: list[FunnelStepOut]


@router.get("/metrics/funnel", response_model=FunnelSummaryOut)
def metrics_funnel(
    range: str = "7d",
    funnel: str = FUNNEL_GROWTH_V1,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> FunnelSummaryOut:
    _require_admin(x_admin_token)
    days = _parse_days(range)
    steps = load_funnel_summary(db, funnel_name=funnel, days=days)
    return FunnelSummaryOut(
        funnel=str(funnel),
        range=f"{days}d",
        steps=[
            FunnelStepOut(step=str(s.get("step")), users=int(s.get("users") or 0))
            for s in steps
        ],
    )


class FunnelDailyPointOut(BaseModel):
    date: str
    steps: dict[str, int] = Field(default_factory=dict)


class FunnelDailyStepStatsOut(BaseModel):
    step: str
    today: int
    avg_7d: float
    yesterday: int
    delta: int
    delta_pct: float | None = None


class FunnelDailyOut(BaseModel):
    funnel: str
    range: str
    steps: list[FunnelDailyStepStatsOut]
    series: list[FunnelDailyPointOut]


@router.get("/metrics/funnel_daily", response_model=FunnelDailyOut)
def metrics_funnel_daily(
    range: str = "7d",
    funnel: str = FUNNEL_SHARE_V1,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> FunnelDailyOut:
    _require_admin(x_admin_token)
    days = _parse_days(range)
    series = load_funnel_daily_series(db, funnel_name=str(funnel), days=days)

    today_counts: dict[str, int] = {}
    yesterday_counts: dict[str, int] = {}
    if series:
        today_counts = dict(series[-1].get("steps") or {})
    if len(series) >= 2:
        yesterday_counts = dict(series[-2].get("steps") or {})

    totals: dict[str, int] = {}
    for row in series[-7:]:
        for k, v in (row.get("steps") or {}).items():
            totals[k] = int(totals.get(k, 0)) + int(v or 0)

    def pct(delta: int, base: int) -> float | None:
        if base <= 0:
            return None
        return float(delta) / float(base)

    ordered_steps: list[str] = []
    if series:
        sample = series[-1].get("steps") or {}
        ordered_steps = [str(k) for k in sample.keys()]

    step_stats: list[FunnelDailyStepStatsOut] = []
    denom = max(1, min(7, len(series)))
    for step in ordered_steps:
        today_v = int(today_counts.get(step, 0))
        yday_v = int(yesterday_counts.get(step, 0))
        d = int(today_v - yday_v)
        step_stats.append(
            FunnelDailyStepStatsOut(
                step=str(step),
                today=today_v,
                avg_7d=float(totals.get(step, 0)) / float(denom),
                yesterday=yday_v,
                delta=d,
                delta_pct=pct(d, yday_v),
            )
        )

    return FunnelDailyOut(
        funnel=str(funnel),
        range=f"{days}d",
        steps=step_stats,
        series=[
            FunnelDailyPointOut(
                date=str(r.get("date")), steps=r.get("steps") or {}
            )
            for r in series
        ],
    )


class MetricsRollupOut(BaseModel):
    ok: bool = True
    range: str
    days: int
    start_date: str
    end_date: str


@router.post("/metrics/rollup", response_model=MetricsRollupOut)
def metrics_rollup(
    range: str = "30d",
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> MetricsRollupOut:
    _require_admin(x_admin_token)
    days = _parse_days(range)
    res = rollup_growth_metrics(db, days=days)
    return MetricsRollupOut(
        ok=True,
        range=f"{days}d",
        days=int(days),
        start_date=res.start_date.isoformat(),
        end_date=res.end_date.isoformat(),
    )


class ExperimentVariantOut(BaseModel):
    id: str
    assigned: int
    converted: int
    conversion_rate: float
    kpis: dict[str, dict[str, float | int]] = Field(default_factory=dict)


class ExperimentStatsOut(BaseModel):
    key: str
    status: str
    variants: list[ExperimentVariantOut]


class ExperimentsOut(BaseModel):
    range: str
    experiments: list[ExperimentStatsOut]


@router.get("/metrics/experiments", response_model=ExperimentsOut)
def metrics_experiments(
    range: str = "7d",
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> ExperimentsOut:
    _require_admin(x_admin_token)
    days = _parse_days(range)
    items = load_experiment_stats(db, days=days)
    return ExperimentsOut(
        range=f"{days}d",
        experiments=[
            ExperimentStatsOut(
                key=str(it.get("key")),
                status=str(it.get("status")),
                variants=[
                    ExperimentVariantOut(
                        id=str(v.get("id")),
                        assigned=int(v.get("assigned") or 0),
                        converted=int(v.get("converted") or 0),
                        conversion_rate=float(v.get("conversion_rate") or 0.0),
                        kpis=v.get("kpis") or {},
                    )
                    for v in (it.get("variants") or [])
                    if isinstance(v, dict)
                ],
            )
            for it in items
            if isinstance(it, dict)
        ],
    )


class ShortsVariantRowOut(BaseModel):
    id: str
    n: int
    completion_rate: float
    share_rate: float
    start_click_rate: float
    primary_kpi_rate: float
    ranked_done_rate: float
    app_open_deeplink_rate: float


class ShortsVariantsTableOut(BaseModel):
    key: str
    variants: list[ShortsVariantRowOut] = Field(default_factory=list)


class ShortsVariantsFiltersOut(BaseModel):
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None


class ShortsVariantsGroupOut(BaseModel):
    utm_source: str
    n_share_open: int = 0
    tables: list[ShortsVariantsTableOut] = Field(default_factory=list)


class ShortsVariantsOut(BaseModel):
    range: str
    start_date: str
    end_date: str
    primary_kpi: str = "ranked_done_per_share_open"
    filters: ShortsVariantsFiltersOut = Field(default_factory=ShortsVariantsFiltersOut)
    available_channels: list[str] = Field(default_factory=list)
    groups: list[ShortsVariantsGroupOut] = Field(default_factory=list)
    tables: list[ShortsVariantsTableOut] = Field(default_factory=list)


@router.get("/metrics/shorts_variants", response_model=ShortsVariantsOut)
def metrics_shorts_variants(
    range: str = "7d",
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> ShortsVariantsOut:
    _require_admin(x_admin_token)
    days = _parse_days(range)
    data = load_shorts_variants(
        db,
        days=days,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
    )

    def parse_tables(raw: Any) -> list[ShortsVariantsTableOut]:
        out: list[ShortsVariantsTableOut] = []
        for t in raw or []:
            if not isinstance(t, dict):
                continue
            rows = []
            for r in t.get("variants") or []:
                if not isinstance(r, dict):
                    continue
                primary_kpi = float(
                    r.get("primary_kpi_rate") or r.get("ranked_done_rate") or 0.0
                )
                rows.append(
                    ShortsVariantRowOut(
                        id=str(r.get("id") or ""),
                        n=int(r.get("n") or 0),
                        completion_rate=float(r.get("completion_rate") or 0.0),
                        share_rate=float(r.get("share_rate") or 0.0),
                        start_click_rate=float(r.get("start_click_rate") or 0.0),
                        primary_kpi_rate=primary_kpi,
                        ranked_done_rate=float(r.get("ranked_done_rate") or 0.0),
                        app_open_deeplink_rate=float(
                            r.get("app_open_deeplink_rate") or 0.0
                        ),
                    )
                )
            out.append(ShortsVariantsTableOut(key=str(t.get("key") or ""), variants=rows))
        return out

    tables = parse_tables(data.get("tables") or [])

    groups_out: list[ShortsVariantsGroupOut] = []
    for g in data.get("groups") or []:
        if not isinstance(g, dict):
            continue
        groups_out.append(
            ShortsVariantsGroupOut(
                utm_source=str(g.get("utm_source") or ""),
                n_share_open=int(g.get("n_share_open") or 0),
                tables=parse_tables(g.get("tables") or []),
            )
        )

    channels: list[str] = []
    for c in data.get("available_channels") or []:
        if isinstance(c, str) and c.strip():
            channels.append(c.strip())

    raw_filters = data.get("filters")
    raw_filters = raw_filters if isinstance(raw_filters, dict) else {}

    return ShortsVariantsOut(
        range=str(data.get("range") or f"{days}d"),
        start_date=str(data.get("start_date") or ""),
        end_date=str(data.get("end_date") or ""),
        primary_kpi=str(data.get("primary_kpi") or "ranked_done_per_share_open"),
        filters=ShortsVariantsFiltersOut(
            utm_source=str(raw_filters.get("utm_source") or "").strip() or None,
            utm_medium=str(raw_filters.get("utm_medium") or "").strip() or None,
            utm_campaign=str(raw_filters.get("utm_campaign") or "").strip() or None,
        ),
        available_channels=channels,
        groups=groups_out,
        tables=tables,
    )


class RecentErrorRowOut(BaseModel):
    path: str
    method: str
    status: int
    count: int
    last_request_id: str | None = None
    last_at: str | None = None


class RecentErrorsOut(BaseModel):
    window_minutes: int
    limit: int
    items: list[RecentErrorRowOut] = Field(default_factory=list)


@router.get("/metrics/errors_recent", response_model=RecentErrorsOut)
def metrics_errors_recent(
    minutes: int = 60,
    limit: int = 10,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> RecentErrorsOut:
    _require_admin(x_admin_token)
    minutes = max(1, min(24 * 60, int(minutes)))
    limit = max(1, min(50, int(limit)))

    items = recent_http_errors_db(db, minutes=minutes, limit=limit)
    out_items: list[RecentErrorRowOut] = []
    for it in items:
        ts = it.get("last_at_s")
        last_at = None
        if isinstance(ts, int) and ts > 0:
            try:
                last_at = datetime.fromtimestamp(ts, tz=UTC).isoformat()
            except Exception:  # noqa: BLE001
                last_at = None
        out_items.append(
            RecentErrorRowOut(
                path=str(it.get("path") or ""),
                method=str(it.get("method") or ""),
                status=int(it.get("status") or 0),
                count=int(it.get("count") or 0),
                last_request_id=(
                    str(it.get("last_request_id") or "").strip() or None
                ),
                last_at=last_at,
            )
        )

    return RecentErrorsOut(window_minutes=minutes, limit=limit, items=out_items)


class RecentAlertRowOut(BaseModel):
    alert_key: str
    summary: str | None = None
    created_at: str
    outbox_id: str | None = None
    outbox_status: str | None = None
    outbox_attempts: int | None = None
    outbox_sent_at: str | None = None
    outbox_last_error: str | None = None


class RecentAlertsOut(BaseModel):
    limit: int
    last_run_at: str | None = None
    last_run: dict[str, Any] = Field(default_factory=dict)
    items: list[RecentAlertRowOut] = Field(default_factory=list)


@router.get("/metrics/alerts_recent", response_model=RecentAlertsOut)
def metrics_alerts_recent(
    limit: int = 12,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> RecentAlertsOut:
    _require_admin(x_admin_token)
    limit = max(1, min(50, int(limit)))

    last_run_at: str | None = None
    last_run: dict[str, Any] = {}
    ev = db.scalar(
        select(Event)
        .where(Event.type == "ops_alerts_check")
        .order_by(desc(Event.created_at))
        .limit(1)
    )
    if ev is not None:
        try:
            last_run_at = ev.created_at.isoformat()
        except Exception:  # noqa: BLE001
            last_run_at = None
        try:
            parsed = orjson.loads(str(ev.payload_json or "{}").encode("utf-8"))
            if isinstance(parsed, dict):
                last_run = parsed
        except Exception:  # noqa: BLE001
            last_run = {}

    rows = db.execute(
        select(AlertSent, DiscordOutbox)
        .outerjoin(DiscordOutbox, DiscordOutbox.id == AlertSent.outbox_id)
        .order_by(desc(AlertSent.created_at))
        .limit(limit)
    ).all()

    items: list[RecentAlertRowOut] = []
    for alert, outbox in rows:
        outbox_id = str(getattr(alert, "outbox_id", "") or "") or None
        out_status = str(getattr(outbox, "status", "") or "") if outbox else None
        out_attempts = int(getattr(outbox, "attempts", 0) or 0) if outbox else None
        out_sent_at = None
        out_last_error = None
        if outbox:
            try:
                out_sent_at = (
                    outbox.sent_at.isoformat() if outbox.sent_at is not None else None
                )
            except Exception:  # noqa: BLE001
                out_sent_at = None
            out_last_error = (
                str(outbox.last_error or "")[:240].strip() or None
            )
        items.append(
            RecentAlertRowOut(
                alert_key=str(alert.alert_key or ""),
                summary=str(alert.summary or "") or None,
                created_at=alert.created_at.isoformat(),
                outbox_id=outbox_id,
                outbox_status=out_status,
                outbox_attempts=out_attempts,
                outbox_sent_at=out_sent_at,
                outbox_last_error=out_last_error,
            )
        )

    return RecentAlertsOut(limit=limit, last_run_at=last_run_at, last_run=last_run, items=items)


class PreflightLatestOut(BaseModel):
    available: bool
    report: dict[str, Any] = Field(default_factory=dict)
    artifact_url: str | None = None
    markdown_url: str | None = None


@router.get("/preflight/latest", response_model=PreflightLatestOut)
def preflight_latest(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> PreflightLatestOut:
    _require_admin(x_admin_token)
    settings = Settings()
    backend = get_storage_backend()

    json_key = "ops/preflight_latest.json"
    md_key = "ops/preflight_latest.md"

    report: dict[str, Any] = {}
    available = False
    try:
        if backend.exists(key=json_key):
            available = True
            raw = backend.get_bytes(key=json_key)
            parsed = orjson.loads(raw)
            if isinstance(parsed, dict):
                report = parsed
    except Exception:  # noqa: BLE001
        available = False
        report = {}

    if not report:
        report = {
            "generated_at": None,
            "ruleset_version": settings.ruleset_version,
            "baseline_pack_hash": None,
            "candidate_pack_hash": None,
            "modes": [],
        }

    artifact_url = None
    markdown_url = None
    try:
        if backend.exists(key=json_key):
            artifact_url = backend.public_url(key=json_key)
        if backend.exists(key=md_key):
            markdown_url = backend.public_url(key=md_key)
    except Exception:  # noqa: BLE001
        artifact_url = None
        markdown_url = None

    return PreflightLatestOut(
        available=available,
        report=report,
        artifact_url=artifact_url,
        markdown_url=markdown_url,
    )


class OpsBuildOfDayEntryOut(BaseModel):
    date: str
    mode: Literal["1v1", "team"]
    source: Literal["override", "auto", "none"]
    picked_blueprint_id: str | None = None
    picked_name: str | None = None
    override_blueprint_id: str | None = None
    auto_blueprint_id: str | None = None


class OpsBuildOfDayOut(BaseModel):
    today: str
    mode: Literal["1v1", "team"]
    storage_key: str = BOD_OVERRIDE_KEY
    entries: list[OpsBuildOfDayEntryOut]


def _bp_name(db: Session, blueprint_id: str | None) -> str | None:
    if not blueprint_id:
        return None
    bp = db.get(Blueprint, blueprint_id)
    if not bp:
        return None
    return str(bp.name or "") or None


@router.get("/build_of_day", response_model=OpsBuildOfDayOut)
def build_of_day_ops(
    mode: Literal["1v1", "team"] = "1v1",
    days: int = 7,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsBuildOfDayOut:
    _require_admin(x_admin_token)
    days = max(1, min(int(days), 30))
    settings = Settings()
    overrides = load_build_of_day_overrides()

    kst_today = datetime.now(UTC).astimezone(KST).date()
    out_entries: list[OpsBuildOfDayEntryOut] = []
    for i in range(days):
        d: date = kst_today - timedelta(days=i)
        date_key = d.isoformat()
        resolved = resolve_build_of_day(
            db,
            date_key=date_key,
            mode=mode,  # type: ignore[arg-type]
            ruleset_version=settings.ruleset_version,
            overrides=overrides,
        )
        picked_id = resolved.picked_blueprint_id
        out_entries.append(
            OpsBuildOfDayEntryOut(
                date=date_key,
                mode=mode,
                source=resolved.source,
                picked_blueprint_id=picked_id,
                picked_name=_bp_name(db, picked_id),
                override_blueprint_id=resolved.override_blueprint_id,
                auto_blueprint_id=resolved.auto_blueprint_id,
            )
        )

    return OpsBuildOfDayOut(today=kst_today.isoformat(), mode=mode, entries=out_entries)


class OpsBuildOfDayOverrideIn(BaseModel):
    mode: Literal["1v1", "team"] = "1v1"
    date: str | None = Field(default=None, max_length=10)
    blueprint_id: str | None = Field(default=None, max_length=120)


@router.post("/build_of_day/override", response_model=OpsBuildOfDayOut)
def build_of_day_override(
    payload: OpsBuildOfDayOverrideIn,
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = DBSession,
) -> OpsBuildOfDayOut:
    _require_admin(x_admin_token)
    settings = Settings()
    mode: Literal["1v1", "team"] = payload.mode

    kst_today = datetime.now(UTC).astimezone(KST).date()
    date_key = payload.date.strip() if payload.date else kst_today.isoformat()
    try:
        # Validate format; keeps storage keys predictable.
        _ = date.fromisoformat(date_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="invalid date (YYYY-MM-DD)"
        ) from exc

    bid = (payload.blueprint_id or "").strip() or None
    if bid:
        bp = db.get(Blueprint, bid)
        if not bp or bp.status != "submitted":
            raise HTTPException(status_code=400, detail="blueprint not found")
        if str(bp.mode) != str(mode):
            raise HTTPException(status_code=400, detail="mode mismatch")
        if str(bp.ruleset_version) != str(settings.ruleset_version):
            raise HTTPException(status_code=400, detail="ruleset mismatch")
        if str(bp.user_id or "").startswith("bot_"):
            raise HTTPException(status_code=400, detail="bot blueprints not allowed")
        hidden = db.scalar(
            select(ModerationHide.target_id)
            .where(ModerationHide.target_type == "build")
            .where(ModerationHide.target_id == bid)
            .limit(1)
        )
        if hidden is not None:
            raise HTTPException(status_code=400, detail="blueprint is hidden")

    overrides = load_build_of_day_overrides()
    now = datetime.now(UTC)
    overrides.setdefault("v", 1)
    root = overrides.setdefault("overrides", {})
    if not isinstance(root, dict):
        root = {}
        overrides["overrides"] = root

    day = root.get(date_key)
    if not isinstance(day, dict):
        day = {}
        root[date_key] = day

    if bid:
        day[str(mode)] = {"blueprint_id": bid, "set_at": now.isoformat()}
    else:
        day.pop(str(mode), None)
        if not day:
            root.pop(date_key, None)

    write_build_of_day_overrides(overrides)

    try:
        log_event(
            db,
            type="ops_build_of_day_override",
            user_id=None,
            request=request,
            payload={
                "mode": str(mode),
                "date": date_key,
                "blueprint_id": bid,
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    return build_of_day_ops(mode=mode, days=7, x_admin_token=x_admin_token, db=db)
