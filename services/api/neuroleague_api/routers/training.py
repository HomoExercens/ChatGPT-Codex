from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import orjson
import ray
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Blueprint, Checkpoint, TrainingRun
from neuroleague_api.rate_limit import check_rate_limit_dual
from neuroleague_api.ray_runtime import ensure_ray
from neuroleague_api.ray_tasks import training_job
from neuroleague_sim.models import BlueprintSpec

router = APIRouter(prefix="/api/training", tags=["training"])


class TrainingRunOut(BaseModel):
    id: str
    mode: Literal["1v1", "team"]
    plan: str
    budget_tokens: int
    status: str
    progress: int
    metrics: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TrainingCreateRequest(BaseModel):
    mode: Literal["1v1", "team"] = "1v1"
    plan: str = "Stable"
    budget_tokens: int = Field(default=500, ge=100, le=5000)


def _maybe_refresh_ray_status(db: Session, tr: TrainingRun) -> None:
    if tr.status not in ("queued", "running"):
        return
    if not tr.ray_job_id:
        return

    ensure_ray()

    raw = tr.ray_job_id.strip()
    if raw.startswith("ObjectRef(") and raw.endswith(")"):
        raw = raw[len("ObjectRef(") : -1]
    try:
        obj_ref = ray.ObjectRef.from_hex(raw)
    except Exception:  # noqa: BLE001
        return

    ready, _ = ray.wait([obj_ref], timeout=0)
    if not ready:
        return

    try:
        ray.get(obj_ref)
    except Exception as exc:  # noqa: BLE001
        now = datetime.now(UTC)
        tr.status = "failed"
        tr.ended_at = now
        tr.updated_at = now
        tr.metrics_json = orjson.dumps({"error": str(exc)}).decode("utf-8")
        db.add(tr)
        db.commit()


@router.get("/runs", response_model=list[TrainingRunOut])
def list_runs(
    user_id: str = CurrentUserId, db: Session = DBSession
) -> list[TrainingRunOut]:
    runs = db.scalars(
        select(TrainingRun)
        .where(TrainingRun.user_id == user_id)
        .order_by(desc(TrainingRun.created_at))
        .limit(50)
    ).all()
    out: list[TrainingRunOut] = []
    for tr in runs:
        out.append(
            TrainingRunOut(
                id=tr.id,
                mode=tr.mode,  # type: ignore[arg-type]
                plan=tr.plan,
                budget_tokens=tr.budget_tokens,
                status=tr.status,
                progress=tr.progress,
                metrics=orjson.loads(tr.metrics_json) if tr.metrics_json else {},
                created_at=tr.created_at,
                updated_at=tr.updated_at,
            )
        )
    return out


@router.post("/runs", response_model=TrainingRunOut)
def create_run(
    request: Request,
    req: TrainingCreateRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> TrainingRunOut:
    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="training_runs",
        per_minute_user=int(settings.rate_limit_training_runs_per_minute),
        per_hour_user=int(settings.rate_limit_training_runs_per_hour),
        per_minute_ip=int(settings.rate_limit_training_runs_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_training_runs_per_hour_ip),
    )
    now = datetime.now(UTC)
    run_id = f"tr_{uuid4().hex}"

    tr = TrainingRun(
        id=run_id,
        user_id=user_id,
        ruleset_version=settings.ruleset_version,
        mode=req.mode,
        plan=req.plan,
        budget_tokens=req.budget_tokens,
        status="queued",
        progress=0,
        metrics_json="{}",
        created_at=now,
        updated_at=now,
        started_at=None,
        ended_at=None,
        ray_job_id=None,
    )
    db.add(tr)
    db.commit()

    ensure_ray()
    e2e_fast = os.environ.get("NEUROLEAGUE_E2E_FAST") == "1"
    iterations = 1 if e2e_fast else max(2, min(10, req.budget_tokens // 100))
    obj_ref = training_job.remote(
        training_run_id=run_id,
        db_url=settings.db_url,
        artifacts_dir=settings.artifacts_dir,
        mode=req.mode,
        iterations=iterations,
    )
    tr.ray_job_id = obj_ref.hex()
    tr.status = "running"
    tr.started_at = now
    tr.updated_at = now
    db.add(tr)
    db.commit()

    return TrainingRunOut(
        id=tr.id,
        mode=tr.mode,  # type: ignore[arg-type]
        plan=tr.plan,
        budget_tokens=tr.budget_tokens,
        status=tr.status,
        progress=tr.progress,
        metrics={},
        created_at=tr.created_at,
        updated_at=tr.updated_at,
    )


@router.get("/runs/{run_id}", response_model=TrainingRunOut)
def get_run(
    run_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> TrainingRunOut:
    tr = db.get(TrainingRun, run_id)
    if not tr or tr.user_id != user_id:
        raise HTTPException(status_code=404, detail="Training run not found")
    _maybe_refresh_ray_status(db, tr)
    return TrainingRunOut(
        id=tr.id,
        mode=tr.mode,  # type: ignore[arg-type]
        plan=tr.plan,
        budget_tokens=tr.budget_tokens,
        status=tr.status,
        progress=tr.progress,
        metrics=orjson.loads(tr.metrics_json) if tr.metrics_json else {},
        created_at=tr.created_at,
        updated_at=tr.updated_at,
    )


def _set_status(db: Session, run_id: str, user_id: str, status: str) -> dict[str, Any]:
    tr = db.get(TrainingRun, run_id)
    if not tr or tr.user_id != user_id:
        raise HTTPException(status_code=404, detail="Training run not found")
    tr.status = status
    tr.updated_at = datetime.now(UTC)
    db.add(tr)
    db.commit()
    return {"ok": True, "status": tr.status}


@router.post("/runs/{run_id}/pause")
def pause(
    run_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    return _set_status(db, run_id, user_id, "paused")


@router.post("/runs/{run_id}/resume")
def resume(
    run_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    return _set_status(db, run_id, user_id, "running")


@router.post("/runs/{run_id}/stop")
def stop(
    run_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    return _set_status(db, run_id, user_id, "stopped")


@router.get("/runs/{run_id}/checkpoints")
def list_checkpoints(
    run_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    tr = db.get(TrainingRun, run_id)
    if not tr or tr.user_id != user_id:
        raise HTTPException(status_code=404, detail="Training run not found")
    rows = db.scalars(
        select(Checkpoint)
        .where(Checkpoint.training_run_id == run_id)
        .order_by(desc(Checkpoint.step))
    ).all()
    return {
        "checkpoints": [
            {
                "id": c.id,
                "step": c.step,
                "metrics": orjson.loads(c.metrics_json) if c.metrics_json else {},
                "artifact_path": c.artifact_path,
                "created_at": c.created_at,
            }
            for c in rows
        ]
    }


class ToBlueprintRequest(BaseModel):
    name: str | None = None
    checkpoint_id: str | None = None


def _candidate_blueprint_spec(
    *, run_id: str, mode: str, checkpoint_id: str | None
) -> BlueprintSpec:
    from neuroleague_sim.catalog import CREATURES, ITEMS

    creature_ids = sorted(CREATURES.keys())
    weapons = sorted([iid for iid, idef in ITEMS.items() if idef.slot == "weapon"])
    armors = sorted([iid for iid, idef in ITEMS.items() if idef.slot == "armor"])
    utilities = sorted([iid for iid, idef in ITEMS.items() if idef.slot == "utility"])

    # Deterministic blueprint generation for v1: derive a stable build from the run id.
    seed_msg = f"{run_id}:{checkpoint_id or 'latest'}:{mode}".encode("utf-8")
    seed = int.from_bytes(
        hashlib.sha256(seed_msg).digest()[:8],
        "little",
        signed=False,
    )

    def pick(lst: list[str], offset: int) -> str | None:
        if not lst:
            return None
        return lst[(seed + offset) % len(lst)]

    team_size = 1 if mode == "1v1" else 3
    used: set[str] = set()
    team: list[dict[str, Any]] = []
    for i in range(team_size):
        cid = pick(creature_ids, i) or creature_ids[0]
        if cid in used:
            cid = pick(creature_ids, i + 7) or creature_ids[0]
        used.add(cid)
        team.append(
            {
                "creature_id": cid,
                "formation": "front" if i < 2 else "back",
                "items": {
                    "weapon": pick(weapons, 3),
                    "armor": pick(armors, 5),
                    "utility": pick(utilities, 9),
                },
            }
        )

    return BlueprintSpec(mode=mode, team=team)


@router.post("/runs/{run_id}/to-blueprint")
def to_blueprint(
    run_id: str,
    req: ToBlueprintRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    tr = db.get(TrainingRun, run_id)
    if not tr or tr.user_id != user_id:
        raise HTTPException(status_code=404, detail="Training run not found")
    checkpoint_id = req.checkpoint_id
    if checkpoint_id is None:
        checkpoint_id = db.scalar(
            select(Checkpoint.id)
            .where(Checkpoint.training_run_id == run_id)
            .order_by(desc(Checkpoint.step))
            .limit(1)
        )

    ckpt: Checkpoint | None = None
    if checkpoint_id:
        ckpt = db.get(Checkpoint, checkpoint_id)
        if not ckpt or ckpt.training_run_id != tr.id:
            raise HTTPException(status_code=404, detail="Checkpoint not found")

    from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256

    meta: dict[str, Any] = {
        "source": {
            "training_run_id": run_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint_path": ckpt.artifact_path if ckpt else None,
        }
    }

    spec: BlueprintSpec
    if ckpt and ckpt.artifact_path:
        try:
            ensure_ray()
            from neuroleague_rl.env import DraftBattleParallelEnv
            from neuroleague_rl.infer import run_draft_policy_inference

            seed_msg = f"{run_id}:{checkpoint_id}:{tr.mode}:draft".encode("utf-8")
            draft_seed = int.from_bytes(
                hashlib.sha256(seed_msg).digest()[:8], "little", signed=False
            )

            info = run_draft_policy_inference(
                checkpoint_path=ckpt.artifact_path, mode=tr.mode, seed=draft_seed
            )
            draft_spec = info.get("draft_spec_a")
            if not isinstance(draft_spec, dict):
                raise RuntimeError("checkpoint inference did not return draft_spec_a")
            spec = BlueprintSpec.model_validate(draft_spec)

            meta.update(
                {
                    "draft_env": DraftBattleParallelEnv.metadata.get("name"),
                    "draft_seed": draft_seed,
                    "draft_log": info.get("draft_log_a", []),
                    "note": "policy_inference",
                }
            )
        except Exception as exc:  # noqa: BLE001
            spec = _candidate_blueprint_spec(
                run_id=run_id, mode=tr.mode, checkpoint_id=checkpoint_id
            )
            meta.update(
                {
                    "note": "fallback_deterministic",
                    "error": str(exc)[:500],
                }
            )
    else:
        spec = _candidate_blueprint_spec(
            run_id=run_id, mode=tr.mode, checkpoint_id=checkpoint_id
        )
        meta.update({"note": "fallback_deterministic", "error": "missing_checkpoint"})

    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())
    from neuroleague_api.build_code import encode_build_code

    build_code = encode_build_code(spec=spec)

    now = datetime.now(UTC)
    blueprint_id = f"bp_{uuid4().hex}"
    bp = Blueprint(
        id=blueprint_id,
        user_id=user_id,
        name=req.name
        or f"Trained: {tr.plan} ({tr.mode})"
        + (f" @ {checkpoint_id}" if checkpoint_id else ""),
        mode=tr.mode,
        ruleset_version=spec.ruleset_version,
        status="draft",
        spec_json=spec_json,
        spec_hash=spec_hash,
        meta_json=orjson.dumps(meta).decode("utf-8"),
        forked_from_id=None,
        build_code=build_code,
        created_at=now,
        updated_at=now,
    )
    db.add(bp)
    db.commit()
    return {"blueprint_id": bp.id, "spec_hash": bp.spec_hash}


class BenchmarkRequest(BaseModel):
    checkpoint_id: str | None = None


@router.post("/runs/{run_id}/benchmark")
def benchmark(
    run_id: str,
    req: BenchmarkRequest = Body(default_factory=BenchmarkRequest),
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    tr = db.get(TrainingRun, run_id)
    if not tr or tr.user_id != user_id:
        raise HTTPException(status_code=404, detail="Training run not found")
    if req.checkpoint_id:
        ckpt = db.get(Checkpoint, req.checkpoint_id)
        if not ckpt or ckpt.training_run_id != tr.id:
            raise HTTPException(status_code=404, detail="Checkpoint not found")

    from neuroleague_sim.canonical import canonical_sha256
    from neuroleague_sim.models import BlueprintSpec
    from neuroleague_sim.simulate import simulate_match

    def bot_specs(mode: str) -> list[tuple[str, str, dict[str, Any]]]:
        if mode == "team":
            return [
                (
                    "bot_guard",
                    "Bulwark Line",
                    {
                        "mode": "team",
                        "team": [
                            {
                                "creature_id": "slime_knight",
                                "formation": "front",
                                "items": {
                                    "weapon": None,
                                    "armor": "reinforced_plate",
                                    "utility": None,
                                },
                            },
                            {
                                "creature_id": "clockwork_golem",
                                "formation": "front",
                                "items": {
                                    "weapon": "plasma_lance",
                                    "armor": None,
                                    "utility": None,
                                },
                            },
                            {
                                "creature_id": "mist_sage",
                                "formation": "back",
                                "items": {
                                    "weapon": None,
                                    "armor": None,
                                    "utility": "healing_drones",
                                },
                            },
                        ],
                    },
                ),
                (
                    "bot_burst",
                    "Burst Trio",
                    {
                        "mode": "team",
                        "team": [
                            {
                                "creature_id": "ember_fox",
                                "formation": "front",
                                "items": {
                                    "weapon": "ember_blade",
                                    "armor": None,
                                    "utility": None,
                                },
                            },
                            {
                                "creature_id": "thornback_boar",
                                "formation": "front",
                                "items": {
                                    "weapon": None,
                                    "armor": "thorn_mail",
                                    "utility": None,
                                },
                            },
                            {
                                "creature_id": "mist_sage",
                                "formation": "back",
                                "items": {
                                    "weapon": None,
                                    "armor": None,
                                    "utility": None,
                                },
                            },
                        ],
                    },
                ),
                (
                    "bot_mystic",
                    "Mystic Circle",
                    {
                        "mode": "team",
                        "team": [
                            {
                                "creature_id": "crystal_weaver",
                                "formation": "front",
                                "items": {
                                    "weapon": "crystal_staff",
                                    "armor": "runic_barrier",
                                    "utility": "targeting_array",
                                },
                            },
                            {
                                "creature_id": "mist_sage",
                                "formation": "front",
                                "items": {
                                    "weapon": None,
                                    "armor": "medic_vest",
                                    "utility": "healing_drones",
                                },
                            },
                            {
                                "creature_id": "field_medic",
                                "formation": "back",
                                "items": {
                                    "weapon": None,
                                    "armor": None,
                                    "utility": "phoenix_ash",
                                },
                            },
                        ],
                    },
                ),
                (
                    "bot_knight",
                    "Knight Brigade",
                    {
                        "mode": "team",
                        "team": [
                            {
                                "creature_id": "slime_knight",
                                "formation": "front",
                                "items": {
                                    "weapon": None,
                                    "armor": "reinforced_plate",
                                    "utility": "phoenix_ash",
                                },
                            },
                            {
                                "creature_id": "sun_paladin",
                                "formation": "front",
                                "items": {
                                    "weapon": "ember_blade",
                                    "armor": "coolant_shell",
                                    "utility": None,
                                },
                            },
                            {
                                "creature_id": "iron_striker",
                                "formation": "back",
                                "items": {
                                    "weapon": "plasma_lance",
                                    "armor": None,
                                    "utility": "adrenaline_module",
                                },
                            },
                        ],
                    },
                ),
                (
                    "bot_beast",
                    "Beast Stampede",
                    {
                        "mode": "team",
                        "team": [
                            {
                                "creature_id": "thornback_boar",
                                "formation": "front",
                                "items": {
                                    "weapon": "thorn_spear",
                                    "armor": "thorn_mail",
                                    "utility": "smoke_emitter",
                                },
                            },
                            {
                                "creature_id": "storm_hawk",
                                "formation": "front",
                                "items": {
                                    "weapon": "ion_repeater",
                                    "armor": None,
                                    "utility": "adrenaline_module",
                                },
                            },
                            {
                                "creature_id": "ember_fox",
                                "formation": "back",
                                "items": {
                                    "weapon": "ember_blade",
                                    "armor": None,
                                    "utility": "targeting_array",
                                },
                            },
                        ],
                    },
                ),
                (
                    "bot_void",
                    "Void Spike",
                    {
                        "mode": "team",
                        "team": [
                            {
                                "creature_id": "void_wisp",
                                "formation": "front",
                                "items": {
                                    "weapon": "void_dagger",
                                    "armor": None,
                                    "utility": "targeting_array",
                                },
                            },
                            {
                                "creature_id": "crystal_weaver",
                                "formation": "front",
                                "items": {
                                    "weapon": None,
                                    "armor": None,
                                    "utility": "healing_drones",
                                },
                            },
                            {
                                "creature_id": "storm_hawk",
                                "formation": "back",
                                "items": {
                                    "weapon": "ion_repeater",
                                    "armor": None,
                                    "utility": None,
                                },
                            },
                        ],
                    },
                ),
            ]
        return [
            (
                "bot_mech",
                "Mech Counter",
                {
                    "mode": "1v1",
                    "team": [
                        {
                            "creature_id": "clockwork_golem",
                            "formation": "front",
                            "items": {
                                "weapon": "plasma_lance",
                                "armor": "reinforced_plate",
                                "utility": "targeting_array",
                            },
                        }
                    ],
                },
            ),
            (
                "bot_ember",
                "Ember Rush",
                {
                    "mode": "1v1",
                    "team": [
                        {
                            "creature_id": "ember_fox",
                            "formation": "front",
                            "items": {
                                "weapon": "ember_blade",
                                "armor": None,
                                "utility": None,
                            },
                        }
                    ],
                },
            ),
            (
                "bot_vine",
                "Vine Wall",
                {
                    "mode": "1v1",
                    "team": [
                        {
                            "creature_id": "thornback_boar",
                            "formation": "front",
                            "items": {
                                "weapon": None,
                                "armor": "thorn_mail",
                                "utility": None,
                            },
                        }
                    ],
                },
            ),
            (
                "bot_mist",
                "Mist Sustain",
                {
                    "mode": "1v1",
                    "team": [
                        {
                            "creature_id": "mist_sage",
                            "formation": "front",
                            "items": {
                                "weapon": None,
                                "armor": None,
                                "utility": "healing_drones",
                            },
                        }
                    ],
                },
            ),
            (
                "bot_slime",
                "Slime Baseline",
                {
                    "mode": "1v1",
                    "team": [
                        {
                            "creature_id": "slime_knight",
                            "formation": "front",
                            "items": {"weapon": None, "armor": None, "utility": None},
                        }
                    ],
                },
            ),
            (
                "bot_crit",
                "Crit Gamble",
                {
                    "mode": "1v1",
                    "team": [
                        {
                            "creature_id": "ember_fox",
                            "formation": "front",
                            "items": {
                                "weapon": "plasma_lance",
                                "armor": None,
                                "utility": "targeting_array",
                            },
                        }
                    ],
                },
            ),
        ]

    spec_a = _candidate_blueprint_spec(
        run_id=run_id, mode=tr.mode, checkpoint_id=req.checkpoint_id
    )
    spec_hash = canonical_sha256(spec_a.model_dump())
    results: list[dict[str, Any]] = []
    wins = 0
    losses = 0
    draws = 0
    for bot_id, bot_name, bot_spec_dict in bot_specs(tr.mode):
        spec_b = BlueprintSpec.model_validate(bot_spec_dict)
        replay = simulate_match(
            match_id=f"bench:{run_id}:{bot_id}",
            seed_index=0,
            blueprint_a=spec_a,
            blueprint_b=spec_b,
        )
        winner = replay.end_summary.winner
        if winner == "A":
            wins += 1
        elif winner == "B":
            losses += 1
        else:
            draws += 1
        results.append(
            {
                "bot_id": bot_id,
                "bot_name": bot_name,
                "winner": winner,
                "digest": replay.digest,
                "highlights": [h.model_dump() for h in replay.highlights],
            }
        )

    return {
        "summary": {"wins": wins, "losses": losses, "draws": draws},
        "results": results,
        "candidate_spec_hash": spec_hash,
    }
