from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import orjson
from sqlalchemy.orm import Session

from neuroleague_api.elo import update_elo
from neuroleague_api.eventlog import log_event
from neuroleague_api.models import Match, Rating, Replay
from neuroleague_api.storage import save_replay_json
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.modifiers import select_match_modifiers
from neuroleague_sim.simulate import simulate_match


def _get_or_create_rating(db: Session, *, user_id: str, mode: str) -> Rating:
    rating = db.get(Rating, {"user_id": user_id, "mode": mode})
    if rating:
        return rating
    rating = Rating(
        user_id=user_id,
        mode=mode,
        elo=1000,
        games_played=0,
        updated_at=datetime.now(UTC),
    )
    db.add(rating)
    db.commit()
    return rating


def run_match_sync(
    *,
    db: Session,
    match: Match,
    blueprint_a: dict[str, Any],
    blueprint_b: dict[str, Any],
    user_a_id: str,
    user_b_id: str,
    mode: str,
    ruleset_version: str,
    seed_set_count: int,
    queue_type: str,
    update_ratings: bool,
) -> str:
    now = datetime.now(UTC)
    match.status = "running"
    match.progress = 0
    match.error_message = None
    match.finished_at = None
    db.add(match)
    db.commit()

    spec_a = BlueprintSpec.model_validate(blueprint_a)
    spec_b = BlueprintSpec.model_validate(blueprint_b)

    modifiers: dict[str, Any] | None = None
    try:
        if getattr(match, "portal_id", None):
            aug_a = (
                orjson.loads(getattr(match, "augments_a_json", "[]") or "[]")
                if getattr(match, "augments_a_json", None) is not None
                else []
            )
            aug_b = (
                orjson.loads(getattr(match, "augments_b_json", "[]") or "[]")
                if getattr(match, "augments_b_json", None) is not None
                else []
            )
            if isinstance(aug_a, list) and isinstance(aug_b, list):
                modifiers = {
                    "portal_id": str(getattr(match, "portal_id", "") or ""),
                    "augments_a": aug_a,
                    "augments_b": aug_b,
                }
    except Exception:  # noqa: BLE001
        modifiers = None

    if modifiers is None:
        modifiers = select_match_modifiers(str(match.id))
        try:
            match.portal_id = str(modifiers.get("portal_id") or "")
            match.augments_a_json = orjson.dumps(modifiers.get("augments_a") or []).decode(
                "utf-8"
            )
            match.augments_b_json = orjson.dumps(modifiers.get("augments_b") or []).decode(
                "utf-8"
            )
            db.add(match)
            db.commit()
        except Exception:  # noqa: BLE001
            pass

    wins_a = 0
    wins_b = 0
    replay_for_view: dict[str, Any] | None = None
    replay_digest = ""

    for seed_index in range(max(1, int(seed_set_count))):
        replay = simulate_match(
            match_id=str(match.id),
            seed_index=int(seed_index),
            blueprint_a=spec_a,
            blueprint_b=spec_b,
            modifiers=modifiers,
        )
        if seed_index == 0:
            replay_for_view = replay.model_dump()
            replay_digest = str(replay.digest)

        if replay.end_summary.winner == "A":
            wins_a += 1
        elif replay.end_summary.winner == "B":
            wins_b += 1

        try:
            match.status = "running"
            match.progress = int(((seed_index + 1) / max(1, int(seed_set_count))) * 100)
            db.add(match)
            db.commit()
        except Exception:  # noqa: BLE001
            pass

    if wins_a > wins_b:
        result: Literal["A", "B", "draw"] = "A"
        score_a = 1.0
    elif wins_b > wins_a:
        result = "B"
        score_a = 0.0
    else:
        result = "draw"
        score_a = 0.5

    if replay_for_view is None or not replay_digest:
        raise RuntimeError("Replay generation failed")

    replay_id = f"r_{uuid4().hex}"
    artifact_path = save_replay_json(replay_id=replay_id, payload=replay_for_view)

    db.add(
        Replay(
            id=replay_id,
            match_id=str(match.id),
            artifact_path=str(artifact_path),
            digest=str(replay_digest),
            created_at=now,
        )
    )

    elo_delta_a = 0
    elo_delta_b = 0
    if update_ratings:
        rating_a = _get_or_create_rating(db, user_id=str(user_a_id), mode=str(mode))
        rating_b = _get_or_create_rating(db, user_id=str(user_b_id), mode=str(mode))
        elo = update_elo(
            rating_a=int(rating_a.elo or 1000),
            rating_b=int(rating_b.elo or 1000),
            score_a=float(score_a),
            games_played_a=int(rating_a.games_played or 0),
            games_played_b=int(rating_b.games_played or 0),
        )
        rating_a.elo = int(elo.new_a)
        rating_a.games_played = int(rating_a.games_played or 0) + 1
        rating_a.updated_at = now

        rating_b.elo = int(elo.new_b)
        rating_b.games_played = int(rating_b.games_played or 0) + 1
        rating_b.updated_at = now

        elo_delta_a = int(elo.delta_a)
        elo_delta_b = int(elo.delta_b)
        db.add(rating_a)
        db.add(rating_b)

    match.status = "done"
    match.progress = 100
    match.ruleset_version = str(ruleset_version)
    match.mode = str(mode)
    match.result = str(result)
    match.elo_delta_a = int(elo_delta_a)
    match.elo_delta_b = int(elo_delta_b)
    match.finished_at = now
    db.add(match)

    try:
        if str(queue_type) == "ranked":
            log_event(
                db,
                type="ranked_done",
                user_id=str(user_a_id),
                request=None,
                payload={
                    "match_id": str(match.id),
                    "mode": str(mode or ""),
                    "result": str(result),
                    "elo_delta_a": int(elo_delta_a),
                },
                now=now,
            )
            log_event(
                db,
                type="match_done",
                user_id=str(user_a_id),
                request=None,
                payload={
                    "match_id": str(match.id),
                    "queue_type": "ranked",
                    "mode": str(mode or ""),
                    "result": str(result),
                },
                now=now,
            )
        elif str(queue_type) == "challenge":
            log_event(
                db,
                type="challenge_done",
                user_id=str(user_a_id),
                request=None,
                payload={
                    "match_id": str(match.id),
                    "queue_type": "challenge",
                    "mode": str(mode or ""),
                    "result": str(result),
                },
                now=now,
            )
    except Exception:  # noqa: BLE001
        pass

    db.commit()
    return replay_id

