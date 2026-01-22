from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.eventlog import log_event
from neuroleague_api.experiments import assign_experiment

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class ExperimentAssignmentOut(BaseModel):
    variant: str
    config: dict[str, Any] = Field(default_factory=dict)


@router.get("/assign", response_model=dict[str, ExperimentAssignmentOut])
def assign(
    request: Request,
    keys: str,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, ExperimentAssignmentOut]:
    raw = [k.strip() for k in str(keys or "").split(",") if k.strip()]
    # Avoid abuse/oversized responses.
    wanted = [k[:64] for k in raw][:20]
    if not wanted:
        return {}

    subject_type = "guest" if str(user_id or "").startswith("guest_") else "user"
    out: dict[str, ExperimentAssignmentOut] = {}
    exposed: list[tuple[str, str]] = []
    for key in wanted:
        variant, cfg, is_new = assign_experiment(
            db,
            subject_type=subject_type,
            subject_id=str(user_id),
            experiment_key=key,
        )
        out[key] = ExperimentAssignmentOut(variant=variant, config=cfg)
        if is_new:
            exposed.append((key, variant))

    for key, variant in exposed:
        log_event(
            db,
            type="experiment_exposed",
            user_id=user_id,
            request=request,
            payload={"experiment_key": key, "variant": variant},
        )
    if exposed:
        db.commit()

    return out
