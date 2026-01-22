from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.build_code import (
    build_code_hash,
    decode_build_code_payload,
    encode_build_code,
)
from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import Blueprint
from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
from neuroleague_sim.models import BlueprintSpec

router = APIRouter(prefix="/api/build_code", tags=["build_code"])


class DecodeBuildCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=32_768)


class BuildCodeWarning(BaseModel):
    type: str
    message: str
    expected: str | None = None
    got: str | None = None


class DecodeBuildCodeOut(BaseModel):
    ok: bool
    error: str | None = None
    warnings: list[BuildCodeWarning] = Field(default_factory=list)
    blueprint_spec: dict[str, Any] | None = None
    ruleset_version: str | None = None
    pack_hash: str | None = None
    mode: Literal["1v1", "team"] | None = None


def _active_pack_hash() -> str | None:
    try:
        from neuroleague_sim.pack_loader import active_pack_hash

        return active_pack_hash()
    except Exception:  # noqa: BLE001
        return None


def _warnings_for(
    *, payload: dict[str, Any], spec: BlueprintSpec
) -> list[BuildCodeWarning]:
    settings = Settings()
    warnings: list[BuildCodeWarning] = []

    payload_ruleset = str(payload.get("ruleset_version") or spec.ruleset_version or "")
    if payload_ruleset and payload_ruleset != settings.ruleset_version:
        warnings.append(
            BuildCodeWarning(
                type="ruleset_mismatch",
                message="Ruleset version differs from the server.",
                expected=str(settings.ruleset_version),
                got=payload_ruleset,
            )
        )

    payload_pack = payload.get("pack_hash")
    pack_hash = str(payload_pack) if isinstance(payload_pack, str) else None
    active = _active_pack_hash()
    if not pack_hash:
        warnings.append(
            BuildCodeWarning(
                type="pack_hash_missing",
                message="Build code has no pack_hash; importing may vary across patches.",
            )
        )
    elif active and pack_hash != active:
        warnings.append(
            BuildCodeWarning(
                type="pack_hash_mismatch",
                message="Pack hash differs from the server.",
                expected=active,
                got=pack_hash,
            )
        )

    payload_mode = payload.get("mode")
    mode = str(payload_mode) if isinstance(payload_mode, str) else None
    if mode and mode != str(spec.mode):
        warnings.append(
            BuildCodeWarning(
                type="mode_mismatch",
                message="Mode in payload differs from spec.",
                expected=str(spec.mode),
                got=mode,
            )
        )

    return warnings


@router.post("/decode", response_model=DecodeBuildCodeOut)
def decode_endpoint(
    req: DecodeBuildCodeIn, _user_id: str = CurrentUserId
) -> DecodeBuildCodeOut:
    try:
        payload = decode_build_code_payload(build_code=req.code)
        spec_raw = payload.get("spec")
        spec = BlueprintSpec.model_validate(spec_raw)
        warnings = _warnings_for(payload=payload, spec=spec)
        payload_pack = payload.get("pack_hash")
        pack_hash = str(payload_pack) if isinstance(payload_pack, str) else None
        payload_mode = payload.get("mode")
        mode = str(payload_mode) if isinstance(payload_mode, str) else str(spec.mode)
        return DecodeBuildCodeOut(
            ok=True,
            warnings=warnings,
            blueprint_spec=spec.model_dump(),
            ruleset_version=str(payload.get("ruleset_version") or spec.ruleset_version),
            pack_hash=pack_hash,
            mode=mode if mode in ("1v1", "team") else str(spec.mode),
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)[:240] or "invalid build code"
        return DecodeBuildCodeOut(ok=False, error=msg)


class ImportBuildCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=32_768)
    name: str | None = Field(default=None, min_length=1, max_length=64)


class ImportBuildCodeOut(BaseModel):
    ok: bool
    warnings: list[BuildCodeWarning] = Field(default_factory=list)
    blueprint: dict[str, Any] | None = None


@router.post("/import", response_model=ImportBuildCodeOut)
def import_endpoint(
    req: ImportBuildCodeIn,
    request: Request,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ImportBuildCodeOut:
    try:
        payload = decode_build_code_payload(build_code=req.code)
        spec_raw = payload.get("spec")
        spec = BlueprintSpec.model_validate(spec_raw)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)[:240] or "invalid build code"
        return ImportBuildCodeOut(ok=False, warnings=[], blueprint={"error": msg})

    warnings = _warnings_for(payload=payload, spec=spec)
    settings = Settings()
    origin_ruleset = str(payload.get("ruleset_version") or spec.ruleset_version or "")
    origin_pack_raw = payload.get("pack_hash")
    origin_pack = str(origin_pack_raw) if isinstance(origin_pack_raw, str) else None
    origin_mode = str(payload.get("mode") or spec.mode or "")

    # Safe-by-default: import into the current server ruleset (unless already matching).
    if spec.ruleset_version != settings.ruleset_version:
        spec = spec.model_copy(update={"ruleset_version": settings.ruleset_version})
        warnings.append(
            BuildCodeWarning(
                type="ruleset_imported_into_current",
                message="Imported into the server ruleset_version.",
                expected=str(settings.ruleset_version),
                got=origin_ruleset,
            )
        )

    now = datetime.now(UTC)
    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())

    parent = db.scalar(
        select(Blueprint)
        .where(Blueprint.status == "submitted")
        .where(Blueprint.mode == str(spec.mode))
        .where(Blueprint.ruleset_version == str(settings.ruleset_version))
        .where(Blueprint.spec_hash == str(spec_hash))
        .order_by(
            desc(Blueprint.submitted_at), desc(Blueprint.updated_at), Blueprint.id.asc()
        )
        .limit(1)
    )
    forked_from_id = str(parent.id) if parent else None

    origin_hash = build_code_hash(build_code=req.code)
    pack_hash = _active_pack_hash()
    build_code = encode_build_code(spec=spec, pack_hash=pack_hash)

    name = (
        req.name or (f"{parent.name} (Import)" if parent else "Imported Build")
    ).strip()
    if len(name) > 64:
        name = name[:64].rstrip()

    meta = {
        "source": {
            "type": "build_code_import",
            "code_prefix": "NL1",
            "origin_code_hash": origin_hash,
            "origin_ruleset_version": origin_ruleset,
            "origin_pack_hash": origin_pack,
            "origin_mode": origin_mode,
            "matched_blueprint_id": forked_from_id,
            "warnings": [w.model_dump() for w in warnings],
        }
    }

    bp = Blueprint(
        id=f"bp_{uuid4().hex}",
        user_id=user_id,
        name=name,
        mode=str(spec.mode),
        ruleset_version=str(spec.ruleset_version),
        status="draft",
        spec_json=spec_json,
        spec_hash=str(spec_hash),
        meta_json=orjson.dumps(meta).decode("utf-8"),
        forked_from_id=forked_from_id,
        build_code=build_code,
        origin_code_hash=origin_hash,
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
                "source": "build_code_import",
                "blueprint_id": bp.id,
                "matched_blueprint_id": forked_from_id,
                "mode": str(spec.mode),
                "ruleset_version": str(spec.ruleset_version),
                "origin_code_hash": origin_hash,
            },
        )
        try:
            from neuroleague_api.quests_engine import apply_event_to_quests

            apply_event_to_quests(db, event=ev)
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    except Exception:  # noqa: BLE001
        pass

    # Return a BlueprintOut-compatible shape (without importing router models).
    payload_out = {
        "id": bp.id,
        "name": bp.name,
        "mode": bp.mode,
        "ruleset_version": bp.ruleset_version,
        "status": bp.status,
        "spec": orjson.loads(bp.spec_json),
        "spec_hash": bp.spec_hash,
        "meta": meta,
        "forked_from_id": bp.forked_from_id,
        "build_code": bp.build_code,
        "submitted_at": None,
        "updated_at": bp.updated_at.isoformat(),
    }
    return ImportBuildCodeOut(ok=True, warnings=warnings, blueprint=payload_out)
