from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.routers.matches import QueueRequest, QueueResponse, queue_ranked

router = APIRouter(prefix="/api/ranked", tags=["ranked"])


@router.post("/queue", response_model=QueueResponse)
def queue(
    request: Request,
    req: QueueRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> QueueResponse:
    return queue_ranked(request, req, user_id=user_id, db=db)
