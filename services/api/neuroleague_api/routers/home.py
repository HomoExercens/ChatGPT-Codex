from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.elo import division_for_elo
from neuroleague_api.models import Blueprint, Match, Rating, Replay, User, Wallet
from neuroleague_api.storage import load_replay_json

router = APIRouter(prefix="/api/home", tags=["home"])


class RecentMatchRow(BaseModel):
    id: str
    opponent: str
    opponent_archetype: str
    result: str
    elo_change: int
    date: str
    duration: str


class HomeSummaryResponse(BaseModel):
    user: dict
    recent_matches: list[RecentMatchRow]
    meta_cards: list[dict]


def _relative(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    diff = datetime.now(UTC) - dt
    minutes = int(diff.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _format_duration_from_ticks(ticks: int) -> str:
    total_sec = max(0, ticks // 20)
    if total_sec < 60:
        return f"{total_sec}s"
    minutes = total_sec // 60
    seconds = total_sec % 60
    return f"{minutes}m {seconds:02d}s"


@router.get("/summary", response_model=HomeSummaryResponse)
def home_summary(
    user_id: str = CurrentUserId, db: Session = DBSession
) -> HomeSummaryResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    wallet = db.get(Wallet, user_id)
    rating_1v1 = db.get(Rating, {"user_id": user_id, "mode": "1v1"})

    recent = db.scalars(
        select(Match)
        .where(Match.user_a_id == user_id)
        .where(Match.queue_type == "ranked")
        .order_by(desc(Match.created_at))
        .limit(3)
    ).all()
    rows: list[RecentMatchRow] = []
    for m in recent:
        opponent = (
            "Lab_Unknown"
            if not m.user_b_id
            else (
                db.get(User, m.user_b_id).display_name
                if db.get(User, m.user_b_id)
                else "Lab_Unknown"
            )
        )
        opp_bp = db.get(Blueprint, m.blueprint_b_id) if m.blueprint_b_id else None
        replay_row = db.scalar(select(Replay).where(Replay.match_id == m.id))
        duration = "—"
        if replay_row:
            payload = load_replay_json(artifact_path=replay_row.artifact_path)
            duration = _format_duration_from_ticks(
                int(payload.get("end_summary", {}).get("duration_ticks", 0))
            )
        rows.append(
            RecentMatchRow(
                id=m.id,
                opponent=opponent,
                opponent_archetype=opp_bp.name if opp_bp else "Mech Rush",
                result="win"
                if m.result == "A"
                else "loss"
                if m.result == "B"
                else "draw",
                elo_change=m.elo_delta_a,
                date=_relative(m.created_at),
                duration=duration,
            )
        )

    elo = rating_1v1.elo if rating_1v1 else 1000
    return HomeSummaryResponse(
        user={
            "display_name": user.display_name,
            "tokens": wallet.tokens_balance if wallet else 0,
            "division": division_for_elo(elo),
            "elo": elo,
        },
        recent_matches=rows,
        meta_cards=[],
    )
