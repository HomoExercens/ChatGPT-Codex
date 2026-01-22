from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Rating, User

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


class LeaderboardRowOut(BaseModel):
    user_id: str
    display_name: str
    is_guest: bool
    elo: int
    games_played: int


@router.get("", response_model=list[LeaderboardRowOut])
def leaderboard(
    mode: Literal["1v1", "team"] = "1v1",
    limit: int = Query(default=50, ge=1, le=100),
    _user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> list[LeaderboardRowOut]:
    rows = db.execute(
        select(Rating, User)
        .join(User, User.id == Rating.user_id)
        .where(Rating.mode == mode)
        .order_by(Rating.elo.desc(), Rating.games_played.desc(), User.id.asc())
        .limit(int(limit))
    ).all()
    return [
        LeaderboardRowOut(
            user_id=r.user_id,
            display_name=u.display_name,
            is_guest=bool(u.is_guest),
            elo=int(r.elo),
            games_played=int(r.games_played),
        )
        for (r, u) in rows
    ]
