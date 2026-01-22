from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Blueprint, Report, Replay, User

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportRequest(BaseModel):
    target_type: Literal["clip", "profile", "build"]
    target_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=280)


class ReportResponse(BaseModel):
    ok: bool = True
    report_id: str


@router.post("", response_model=ReportResponse)
def create_report(
    req: ReportRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> ReportResponse:
    if req.target_type == "clip":
        if db.get(Replay, req.target_id) is None:
            raise HTTPException(status_code=404, detail="Replay not found")
    elif req.target_type == "profile":
        if db.get(User, req.target_id) is None:
            raise HTTPException(status_code=404, detail="User not found")
    elif req.target_type == "build":
        bp = db.get(Blueprint, req.target_id)
        if bp is None or bp.status != "submitted":
            raise HTTPException(status_code=404, detail="Build not found")

    now = datetime.now(UTC)
    report_id = f"rep_{uuid4().hex}"
    db.add(
        Report(
            id=report_id,
            reporter_user_id=user_id,
            target_type=req.target_type,
            target_id=req.target_id,
            reason=req.reason.strip(),
            created_at=now,
        )
    )
    db.commit()
    return ReportResponse(report_id=report_id)
