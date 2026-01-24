from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import DBSession
from neuroleague_api.hero_clips import recompute_hero_clips


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

