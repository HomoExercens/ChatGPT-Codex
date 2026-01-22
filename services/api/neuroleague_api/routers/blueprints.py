from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.build_code import decode_build_code, encode_build_code
from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import Blueprint, Event, User
from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
from neuroleague_sim.models import BlueprintSpec

router = APIRouter(prefix="/api/blueprints", tags=["blueprints"])


def _active_pack_hash() -> str | None:
    try:
        from neuroleague_sim.pack_loader import active_pack_hash

        return active_pack_hash()
    except Exception:  # noqa: BLE001
        return None


class BlueprintOut(BaseModel):
    id: str
    name: str
    mode: Literal["1v1", "team"]
    ruleset_version: str
    status: str
    spec: dict[str, Any]
    spec_hash: str
    meta: dict[str, Any] = Field(default_factory=dict)
    forked_from_id: str | None = None
    build_code: str | None = None
    submitted_at: datetime | None = None
    updated_at: datetime


class BlueprintCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    mode: Literal["1v1", "team"]
    spec: dict[str, Any] | None = None


def _default_spec(mode: Literal["1v1", "team"]) -> dict[str, Any]:
    if mode == "1v1":
        return {
            "ruleset_version": Settings().ruleset_version,
            "mode": "1v1",
            "team": [
                {"creature_id": "slime_knight", "formation": "front", "items": {}}
            ],
        }
    return {
        "ruleset_version": Settings().ruleset_version,
        "mode": "team",
        "team": [
            {
                "creature_id": "clockwork_golem",
                "formation": "front",
                "items": {"armor": "reinforced_plate"},
            },
            {
                "creature_id": "iron_striker",
                "formation": "front",
                "items": {"weapon": "plasma_lance"},
            },
            {
                "creature_id": "crystal_weaver",
                "formation": "back",
                "items": {"utility": "targeting_array"},
            },
        ],
    }


def _meta_dict(bp: Blueprint) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        meta = orjson.loads(bp.meta_json) if bp.meta_json else {}
    except Exception:  # noqa: BLE001
        meta = {}
    return meta if isinstance(meta, dict) else {}


def _maybe_compute_build_code(
    db: Session, *, bp: Blueprint, spec: BlueprintSpec | None = None
) -> str | None:
    if bp.build_code:
        return bp.build_code
    try:
        if spec is None:
            spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
        bp.build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())
        bp.updated_at = datetime.now(UTC)
        db.add(bp)
        db.commit()
        return bp.build_code
    except Exception:  # noqa: BLE001
        return None


def _out_from_bp(db: Session, *, bp: Blueprint) -> BlueprintOut:
    meta = _meta_dict(bp)
    build_code = _maybe_compute_build_code(db, bp=bp)
    return BlueprintOut(
        id=bp.id,
        name=bp.name,
        mode=bp.mode,  # type: ignore[arg-type]
        ruleset_version=bp.ruleset_version,
        status=bp.status,
        spec=orjson.loads(bp.spec_json),
        spec_hash=bp.spec_hash,
        meta=meta,
        forked_from_id=bp.forked_from_id,
        build_code=build_code,
        submitted_at=bp.submitted_at if bp.status == "submitted" else None,
        updated_at=bp.updated_at,
    )


@router.get("", response_model=list[BlueprintOut])
def list_blueprints(
    user_id: str = CurrentUserId, db: Session = DBSession
) -> list[BlueprintOut]:
    bps = db.scalars(
        select(Blueprint)
        .where(Blueprint.user_id == user_id)
        .where(Blueprint.status != "archived")
        .order_by(desc(Blueprint.updated_at))
    ).all()
    return [_out_from_bp(db, bp=bp) for bp in bps]


@router.post("", response_model=BlueprintOut)
def create_blueprint(
    req: BlueprintCreateRequest, user_id: str = CurrentUserId, db: Session = DBSession
) -> BlueprintOut:
    spec_obj = req.spec if req.spec is not None else _default_spec(req.mode)
    spec = BlueprintSpec.model_validate(spec_obj)
    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())
    build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())

    now = datetime.now(UTC)
    bp = Blueprint(
        id=f"bp_{uuid4().hex}",
        user_id=user_id,
        name=req.name,
        mode=req.mode,
        ruleset_version=spec.ruleset_version,
        status="draft",
        spec_json=spec_json,
        spec_hash=spec_hash,
        meta_json="{}",
        forked_from_id=None,
        build_code=build_code,
        created_at=now,
        updated_at=now,
    )
    db.add(bp)
    db.commit()

    return _out_from_bp(db, bp=bp)


class BlueprintUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    spec: dict[str, Any] | None = None


@router.get("/{blueprint_id}", response_model=BlueprintOut)
def get_blueprint(
    blueprint_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> BlueprintOut:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return _out_from_bp(db, bp=bp)


class BlueprintCodeOut(BaseModel):
    blueprint_id: str
    build_code: str | None = None


@router.get("/{blueprint_id}/code", response_model=BlueprintCodeOut)
def get_blueprint_code(
    blueprint_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> BlueprintCodeOut:
    bp = db.get(Blueprint, blueprint_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    if bp.user_id != user_id and bp.status != "submitted":
        raise HTTPException(status_code=404, detail="Blueprint not found")
    code = _maybe_compute_build_code(db, bp=bp)
    return BlueprintCodeOut(blueprint_id=bp.id, build_code=code)


@router.put("/{blueprint_id}", response_model=BlueprintOut)
def update_blueprint(
    blueprint_id: str,
    req: BlueprintUpdateRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BlueprintOut:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    if bp.status == "archived":
        raise HTTPException(status_code=400, detail="Blueprint is archived")

    if req.name is not None:
        bp.name = req.name

    if req.spec is not None:
        spec = BlueprintSpec.model_validate(req.spec)
        bp.spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
        bp.spec_hash = canonical_sha256(spec.model_dump())
        bp.ruleset_version = spec.ruleset_version
        bp.mode = spec.mode
        bp.build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())
        if bp.status == "submitted":
            bp.status = "draft"

    bp.updated_at = datetime.now(UTC)
    db.add(bp)
    db.commit()

    return _out_from_bp(db, bp=bp)


@router.post("/{blueprint_id}/validate")
def validate_blueprint(
    blueprint_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
    return {
        "ok": True,
        "ruleset_version": bp.ruleset_version,
        "spec_hash": bp.spec_hash,
    }


@router.post("/{blueprint_id}/submit", response_model=BlueprintOut)
def submit_blueprint(
    request: Request,
    blueprint_id: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BlueprintOut:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
    now = datetime.now(UTC)

    # Idempotent: already-submitted blueprints keep their submission timestamp.
    if bp.status == "submitted":
        return _out_from_bp(db, bp=bp)

    settings = Settings()
    cooldown = int(settings.blueprint_submit_cooldown_sec)
    if cooldown > 0:
        last_submitted_at = db.scalar(
            select(Blueprint.submitted_at)
            .where(Blueprint.user_id == user_id)
            .where(Blueprint.mode == bp.mode)
            .where(Blueprint.ruleset_version == bp.ruleset_version)
            .where(Blueprint.submitted_at.is_not(None))  # type: ignore[arg-type]
            .order_by(desc(Blueprint.submitted_at))
            .limit(1)
        )
        if last_submitted_at is not None:
            if getattr(last_submitted_at, "tzinfo", None) is None:
                last_submitted_at = last_submitted_at.replace(tzinfo=UTC)
            elapsed = max(0.0, (now - last_submitted_at).total_seconds())
            if elapsed < cooldown:
                retry_after = int(max(1, cooldown - elapsed))
                db.add(
                    Event(
                        id=f"ev_{uuid4().hex}",
                        user_id=user_id,
                        type="anti_abuse_flag",
                        payload_json=orjson.dumps(
                            {
                                "user_id": user_id,
                                "mode": bp.mode,
                                "reason": "submit_cooldown",
                                "blueprint_id": bp.id,
                                "ruleset_version": bp.ruleset_version,
                                "retry_after_sec": retry_after,
                            }
                        ).decode("utf-8"),
                        created_at=now,
                    )
                )
                db.commit()
                raise HTTPException(
                    status_code=429,
                    detail={"error": "submit_cooldown", "retry_after_sec": retry_after},
                    headers={"Retry-After": str(int(retry_after))},
                )

    bp.status = "submitted"
    bp.submitted_at = now
    bp.updated_at = now
    if not bp.build_code:
        bp.build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())
    db.add(bp)
    db.commit()
    try:
        log_event(
            db,
            type="blueprint_submit",
            user_id=user_id,
            request=request,
            payload={
                "blueprint_id": bp.id,
                "mode": str(bp.mode or ""),
                "ruleset_version": str(bp.ruleset_version or ""),
                "spec_hash": str(bp.spec_hash or ""),
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001
        pass
    return _out_from_bp(db, bp=bp)


@router.post("/{blueprint_id}/archive")
def archive_blueprint(
    blueprint_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    bp.status = "archived"
    bp.updated_at = datetime.now(UTC)
    db.add(bp)
    db.commit()
    return {"ok": True}


@router.post("/{blueprint_id}/duplicate", response_model=BlueprintOut)
def duplicate_blueprint(
    blueprint_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> BlueprintOut:
    bp = db.get(Blueprint, blueprint_id)
    if not bp or bp.user_id != user_id:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    now = datetime.now(UTC)
    build_code: str | None = None
    try:
        spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
        build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())
    except Exception:  # noqa: BLE001
        build_code = None
    new_bp = Blueprint(
        id=f"bp_{uuid4().hex}",
        user_id=user_id,
        name=f"{bp.name} (Copy)",
        mode=bp.mode,
        ruleset_version=bp.ruleset_version,
        status="draft",
        spec_json=bp.spec_json,
        spec_hash=bp.spec_hash,
        meta_json="{}",
        forked_from_id=None,
        build_code=build_code,
        created_at=now,
        updated_at=now,
    )
    db.add(new_bp)
    db.commit()
    return _out_from_bp(db, bp=new_bp)


class BlueprintImportRequest(BaseModel):
    build_code: str = Field(min_length=4, max_length=32_768)
    name: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/import", response_model=BlueprintOut)
def import_blueprint(
    req: BlueprintImportRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BlueprintOut:
    try:
        spec = decode_build_code(build_code=req.build_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = Settings()
    if spec.ruleset_version != settings.ruleset_version:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ruleset_mismatch",
                "expected": settings.ruleset_version,
                "got": spec.ruleset_version,
            },
        )

    now = datetime.now(UTC)
    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())
    build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())

    bp = Blueprint(
        id=f"bp_{uuid4().hex}",
        user_id=user_id,
        name=req.name or "Imported Build",
        mode=spec.mode,
        ruleset_version=spec.ruleset_version,
        status="draft",
        spec_json=spec_json,
        spec_hash=spec_hash,
        meta_json=orjson.dumps(
            {"source": {"type": "build_code_import", "code_prefix": "NL1"}}
        ).decode("utf-8"),
        forked_from_id=None,
        build_code=build_code,
        submitted_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(bp)
    db.commit()

    return _out_from_bp(db, bp=bp)


class BlueprintForkRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/{blueprint_id}/fork", response_model=BlueprintOut)
def fork_blueprint(
    request: Request,
    blueprint_id: str,
    req: BlueprintForkRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> BlueprintOut:
    src = db.get(Blueprint, blueprint_id)
    if not src:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    if src.user_id != user_id and src.status != "submitted":
        raise HTTPException(status_code=404, detail="Blueprint not found")

    try:
        spec = BlueprintSpec.model_validate(orjson.loads(src.spec_json))
        build_code = encode_build_code(spec=spec, pack_hash=_active_pack_hash())
    except Exception:  # noqa: BLE001
        build_code = None

    now = datetime.now(UTC)
    name = req.name or f"{src.name} (Fork)"
    bp = Blueprint(
        id=f"bp_{uuid4().hex}",
        user_id=user_id,
        name=name,
        mode=src.mode,
        ruleset_version=src.ruleset_version,
        status="draft",
        spec_json=src.spec_json,
        spec_hash=src.spec_hash,
        meta_json=orjson.dumps(
            {
                "source": {
                    "type": "fork",
                    "forked_from_id": src.id,
                    "forked_from_user_id": src.user_id,
                }
            }
        ).decode("utf-8"),
        forked_from_id=src.id,
        build_code=build_code,
        submitted_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(bp)
    db.commit()
    try:
        ev = log_event(
            db,
            type="blueprint_fork",
            user_id=user_id,
            request=request,
            payload={
                "source_blueprint_id": src.id,
                "blueprint_id": bp.id,
                "mode": str(bp.mode or ""),
                "ruleset_version": str(bp.ruleset_version or ""),
            },
        )
        try:
            from neuroleague_api.quests_engine import apply_event_to_quests

            apply_event_to_quests(db, event=ev)
        except Exception:  # noqa: BLE001
            pass

        try:
            ev2 = log_event(
                db,
                type="quest_remix_or_beat",
                user_id=user_id,
                request=request,
                payload={"source": "blueprint_fork", "blueprint_id": bp.id},
            )
            try:
                from neuroleague_api.quests_engine import apply_event_to_quests

                apply_event_to_quests(db, event=ev2)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    except Exception:  # noqa: BLE001
        pass
    return _out_from_bp(db, bp=bp)


class LineageNode(BaseModel):
    blueprint_id: str
    name: str
    user_id: str
    display_name: str
    status: str
    submitted_at: datetime | None = None
    forked_from_id: str | None = None
    build_code: str | None = None
    children_count: int = 0
    origin_code_hash: str | None = None


class BlueprintLineageOut(BaseModel):
    blueprint_id: str
    chain: list[LineageNode]
    children: list[LineageNode] = Field(default_factory=list)


@router.get("/{blueprint_id}/lineage", response_model=BlueprintLineageOut)
def lineage(
    blueprint_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> BlueprintLineageOut:
    bp = db.get(Blueprint, blueprint_id)
    if not bp:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    if bp.user_id != user_id and bp.status != "submitted":
        raise HTTPException(status_code=404, detail="Blueprint not found")

    chain: list[Blueprint] = []
    seen: set[str] = set()
    cur: Blueprint | None = bp
    for _ in range(10):
        if not cur or cur.id in seen:
            break
        seen.add(cur.id)
        chain.append(cur)
        if not cur.forked_from_id:
            break
        cur = db.get(Blueprint, cur.forked_from_id)

    user_ids = sorted({c.user_id for c in chain})
    users = (
        db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    )
    user_by_id = {u.id: u for u in users}

    child_counts: dict[str, int] = {}
    try:
        from sqlalchemy import func

        counts = db.execute(
            select(Blueprint.forked_from_id, func.count(Blueprint.id))
            .where(Blueprint.forked_from_id.in_([c.id for c in chain]))
            .group_by(Blueprint.forked_from_id)
        ).all()
        child_counts = {str(pid): int(cnt) for pid, cnt in counts if pid}
    except Exception:  # noqa: BLE001
        child_counts = {}

    out_chain: list[LineageNode] = []
    for node in chain:
        u = user_by_id.get(node.user_id)
        out_chain.append(
            LineageNode(
                blueprint_id=node.id,
                name=node.name,
                user_id=node.user_id,
                display_name=u.display_name if u else "Lab_Unknown",
                status=node.status,
                submitted_at=node.submitted_at if node.status == "submitted" else None,
                forked_from_id=node.forked_from_id,
                build_code=_maybe_compute_build_code(db, bp=node),
                children_count=int(child_counts.get(node.id) or 0),
                origin_code_hash=getattr(node, "origin_code_hash", None),
            )
        )

    child_nodes: list[Blueprint] = []
    try:
        cq = select(Blueprint).where(Blueprint.forked_from_id == bp.id)
        if bp.user_id != user_id:
            cq = cq.where(Blueprint.status == "submitted")
        child_nodes = db.scalars(
            cq.order_by(desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id.asc()).limit(20)
        ).all()
    except Exception:  # noqa: BLE001
        child_nodes = []

    children_counts: dict[str, int] = {}
    if child_nodes:
        try:
            from sqlalchemy import func

            counts = db.execute(
                select(Blueprint.forked_from_id, func.count(Blueprint.id))
                .where(Blueprint.forked_from_id.in_([c.id for c in child_nodes]))
                .group_by(Blueprint.forked_from_id)
            ).all()
            children_counts = {str(pid): int(cnt) for pid, cnt in counts if pid}
        except Exception:  # noqa: BLE001
            children_counts = {}

    extra_user_ids = sorted({c.user_id for c in child_nodes} - set(user_by_id.keys()))
    if extra_user_ids:
        extra_users = db.scalars(select(User).where(User.id.in_(extra_user_ids))).all()
        for u in extra_users:
            user_by_id[u.id] = u

    def _sort_key(n: Blueprint) -> tuple[int, datetime, datetime, str]:
        forks = int(children_counts.get(n.id) or 0)
        sub = n.submitted_at or datetime.fromtimestamp(0, tz=UTC)
        upd = n.updated_at or datetime.fromtimestamp(0, tz=UTC)
        return forks, sub, upd, str(n.id)

    child_nodes_sorted = sorted(child_nodes, key=_sort_key, reverse=True)[:6]
    out_children: list[LineageNode] = []
    for node in child_nodes_sorted:
        u = user_by_id.get(node.user_id)
        out_children.append(
            LineageNode(
                blueprint_id=node.id,
                name=node.name,
                user_id=node.user_id,
                display_name=u.display_name if u else "Lab_Unknown",
                status=node.status,
                submitted_at=node.submitted_at if node.status == "submitted" else None,
                forked_from_id=node.forked_from_id,
                build_code=_maybe_compute_build_code(db, bp=node),
                children_count=int(children_counts.get(node.id) or 0),
                origin_code_hash=getattr(node, "origin_code_hash", None),
            )
        )

    return BlueprintLineageOut(blueprint_id=bp.id, chain=out_chain, children=out_children)
