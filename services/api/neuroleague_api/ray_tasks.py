from __future__ import annotations

import hashlib
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import orjson
import ray


@ray.remote
def simulate_match_job(
    *, match_id: str, seed_index: int, blueprint_a: dict, blueprint_b: dict
) -> dict[str, Any]:
    from neuroleague_sim.models import BlueprintSpec
    from neuroleague_sim.modifiers import select_match_modifiers
    from neuroleague_sim.simulate import simulate_match

    spec_a = BlueprintSpec.model_validate(blueprint_a)
    spec_b = BlueprintSpec.model_validate(blueprint_b)
    modifiers = select_match_modifiers(match_id)
    replay = simulate_match(
        match_id=match_id,
        seed_index=seed_index,
        blueprint_a=spec_a,
        blueprint_b=spec_b,
        modifiers=modifiers,
    )
    return {
        "seed_index": seed_index,
        "winner": replay.end_summary.winner,
        "digest": replay.digest,
        "replay": replay.model_dump() if seed_index == 0 else None,
    }


@ray.remote(max_retries=0)
def ranked_match_job(
    *,
    match_id: str,
    seed_set_count: int,
    blueprint_a: dict,
    blueprint_b: dict,
    user_a_id: str,
    user_b_id: str,
    mode: str,
    ruleset_version: str,
    db_url: str,
    artifacts_dir: str,
    queue_type: str = "ranked",
    update_ratings: bool = True,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.eventlog import log_event
    from neuroleague_api.elo import update_elo
    from neuroleague_api.models import Cosmetic, Match, Rating, Replay, UserCosmetic
    from neuroleague_api.referrals import credit_referral_if_eligible
    from neuroleague_api.storage import save_replay_json
    from neuroleague_sim.models import BlueprintSpec
    from neuroleague_sim.modifiers import select_match_modifiers
    from neuroleague_sim.simulate import simulate_match

    def get_or_create_rating(session, uid: str, mode_: str) -> Rating:
        rating = session.get(Rating, {"user_id": uid, "mode": mode_})
        if rating:
            return rating
        rating = Rating(
            user_id=uid,
            mode=mode_,
            elo=1000,
            games_played=0,
            updated_at=datetime.now(UTC),
        )
        session.add(rating)
        session.commit()
        return rating

    try:
        spec_a = BlueprintSpec.model_validate(blueprint_a)
        spec_b = BlueprintSpec.model_validate(blueprint_b)
        modifiers: dict[str, Any] | None = None

        with SessionLocal() as session:
            m = session.get(Match, match_id)
            if not m:
                return "missing"
            m.status = "running"
            m.progress = 0
            m.error_message = None
            try:
                if getattr(m, "queue_type", None) != queue_type:
                    m.queue_type = queue_type
            except Exception:  # noqa: BLE001
                pass

            # Prefer DB-persisted match modifiers for stability across code changes.
            try:
                if getattr(m, "portal_id", None):
                    aug_a = (
                        orjson.loads(getattr(m, "augments_a_json", "[]") or "[]")
                        if getattr(m, "augments_a_json", None) is not None
                        else []
                    )
                    aug_b = (
                        orjson.loads(getattr(m, "augments_b_json", "[]") or "[]")
                        if getattr(m, "augments_b_json", None) is not None
                        else []
                    )
                    if isinstance(aug_a, list) and isinstance(aug_b, list):
                        modifiers = {
                            "portal_id": str(m.portal_id),
                            "augments_a": aug_a,
                            "augments_b": aug_b,
                        }
            except Exception:  # noqa: BLE001
                modifiers = None

            if modifiers is None:
                modifiers = select_match_modifiers(match_id)
                try:
                    m.portal_id = str(modifiers.get("portal_id") or "")
                    m.augments_a_json = orjson.dumps(
                        modifiers.get("augments_a") or []
                    ).decode("utf-8")
                    m.augments_b_json = orjson.dumps(
                        modifiers.get("augments_b") or []
                    ).decode("utf-8")
                except Exception:  # noqa: BLE001
                    pass

            session.add(m)
            session.commit()

        wins_a = 0
        wins_b = 0
        draws = 0
        replay_for_view: dict[str, Any] | None = None
        replay_digest = ""

        for seed_index in range(seed_set_count):
            replay = simulate_match(
                match_id=match_id,
                seed_index=seed_index,
                blueprint_a=spec_a,
                blueprint_b=spec_b,
                modifiers=modifiers,
            )
            if seed_index == 0:
                replay_for_view = replay.model_dump()
                replay_digest = replay.digest

            if replay.end_summary.winner == "A":
                wins_a += 1
            elif replay.end_summary.winner == "B":
                wins_b += 1
            else:
                draws += 1

            with SessionLocal() as session:
                m = session.get(Match, match_id)
                if m:
                    m.status = "running"
                    m.progress = int(((seed_index + 1) / max(1, seed_set_count)) * 100)
                    session.add(m)
                    session.commit()

        if wins_a > wins_b:
            result = "A"
            score_a = 1.0
        elif wins_b > wins_a:
            result = "B"
            score_a = 0.0
        else:
            result = "draw"
            score_a = 0.5

        if replay_for_view is None:
            raise RuntimeError("Replay generation failed")

        now = datetime.now(UTC)
        replay_id = f"r_{uuid4().hex}"
        artifact_path = save_replay_json(replay_id=replay_id, payload=replay_for_view)

        with SessionLocal() as session:
            m = session.get(Match, match_id)
            if not m:
                return "missing"

            rating_a = get_or_create_rating(session, user_a_id, mode)
            rating_b = get_or_create_rating(session, user_b_id, mode)
            first_ranked_completion_a = (
                bool(update_ratings)
                and str(queue_type) == "ranked"
                and int(getattr(rating_a, "games_played", 0) or 0) == 0
            )
            elo = None
            if update_ratings:
                elo = update_elo(
                    rating_a=rating_a.elo,
                    rating_b=rating_b.elo,
                    score_a=score_a,
                    games_played_a=rating_a.games_played,
                    games_played_b=rating_b.games_played,
                )

            if update_ratings and elo is not None:
                rating_a.elo = elo.new_a
                rating_a.games_played += 1
                rating_a.updated_at = now

                rating_b.elo = elo.new_b
                rating_b.games_played += 1
                rating_b.updated_at = now

            m.status = "done"
            m.progress = 100
            m.ruleset_version = ruleset_version
            m.mode = mode
            m.result = result
            m.elo_delta_a = (
                int(elo.delta_a) if (update_ratings and elo is not None) else 0
            )
            m.elo_delta_b = (
                int(elo.delta_b) if (update_ratings and elo is not None) else 0
            )
            m.finished_at = now
            session.add(m)
            if update_ratings:
                session.add(rating_a)
                session.add(rating_b)
            session.add(
                Replay(
                    id=replay_id,
                    match_id=match_id,
                    artifact_path=artifact_path,
                    digest=replay_digest,
                    created_at=now,
                )
            )

            if first_ranked_completion_a:
                try:
                    credit_referral_if_eligible(
                        session, new_user_id=user_a_id, match_id=match_id, now=now
                    )
                except Exception:  # noqa: BLE001
                    pass

            if queue_type == "tournament":
                try:
                    week = getattr(m, "week_id", None)
                    if not week:
                        year, wk, _ = now.isocalendar()
                        week = f"{int(year)}W{int(wk):02d}"
                        try:
                            m.week_id = week
                        except Exception:  # noqa: BLE001
                            pass
                    cosmetic_id = f"badge_tournament_participant_{week}"
                    if session.get(Cosmetic, cosmetic_id) is None:
                        session.add(
                            Cosmetic(
                                id=cosmetic_id,
                                kind="badge",
                                name=f"Tournament Participant ({week})",
                                asset_path=None,
                                created_at=now,
                            )
                        )
                    if (
                        session.get(
                            UserCosmetic,
                            {"user_id": user_a_id, "cosmetic_id": cosmetic_id},
                        )
                        is None
                    ):
                        session.add(
                            UserCosmetic(
                                user_id=user_a_id,
                                cosmetic_id=cosmetic_id,
                                earned_at=now,
                                source=f"tournament_participation_{week}",
                            )
                        )
                except Exception:  # noqa: BLE001
                    pass

            try:
                if str(queue_type) == "ranked":
                    ev_ranked = log_event(
                        session,
                        type="ranked_done",
                        user_id=user_a_id,
                        request=None,
                        payload={
                            "match_id": match_id,
                            "mode": str(mode or ""),
                            "result": str(result),
                            "elo_delta_a": int(getattr(m, "elo_delta_a", 0) or 0),
                        },
                        now=now,
                    )
                    try:
                        from neuroleague_api.quests_engine import apply_event_to_quests

                        apply_event_to_quests(session, event=ev_ranked)
                    except Exception:  # noqa: BLE001
                        pass

                    ev_match = log_event(
                        session,
                        type="match_done",
                        user_id=user_a_id,
                        request=None,
                        payload={
                            "match_id": match_id,
                            "queue_type": "ranked",
                            "mode": str(mode or ""),
                            "result": str(result),
                        },
                        now=now,
                    )
                    try:
                        from neuroleague_api.quests_engine import apply_event_to_quests

                        apply_event_to_quests(session, event=ev_match)
                    except Exception:  # noqa: BLE001
                        pass
                    if first_ranked_completion_a:
                        log_event(
                            session,
                            type="first_match_done",
                            user_id=user_a_id,
                            request=None,
                            payload={
                                "match_id": match_id,
                                "queue_type": "ranked",
                                "mode": str(mode or ""),
                                "result": str(result),
                            },
                            now=now,
                        )
                elif str(queue_type) == "tournament":
                    ev_tournament = log_event(
                        session,
                        type="tournament_done",
                        user_id=user_a_id,
                        request=None,
                        payload={
                            "match_id": match_id,
                            "mode": str(mode or ""),
                            "week_id": str(getattr(m, "week_id", "") or ""),
                            "result": str(result),
                        },
                        now=now,
                    )
                    try:
                        from neuroleague_api.quests_engine import apply_event_to_quests

                        apply_event_to_quests(session, event=ev_tournament)
                    except Exception:  # noqa: BLE001
                        pass
                elif str(queue_type) == "challenge":
                    ev_challenge = log_event(
                        session,
                        type="challenge_done",
                        user_id=user_a_id,
                        request=None,
                        payload={
                            "match_id": match_id,
                            "mode": str(mode or ""),
                            "result": str(result),
                        },
                        now=now,
                    )
                    try:
                        from neuroleague_api.quests_engine import apply_event_to_quests

                        apply_event_to_quests(session, event=ev_challenge)
                    except Exception:  # noqa: BLE001
                        pass

                    ev_match = log_event(
                        session,
                        type="match_done",
                        user_id=user_a_id,
                        request=None,
                        payload={
                            "match_id": match_id,
                            "queue_type": "challenge",
                            "mode": str(mode or ""),
                            "result": str(result),
                        },
                        now=now,
                    )
                    try:
                        from neuroleague_api.quests_engine import apply_event_to_quests

                        apply_event_to_quests(session, event=ev_match)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass

            session.commit()

        try:
            from neuroleague_api.core.config import Settings

            cfg = Settings()
            allowed = {
                t.strip()
                for t in str(cfg.best_clip_prewarm_queue_types or "").split(",")
                if t.strip()
            }
            prewarm_enabled = bool(cfg.best_clip_prewarm_enabled) and (
                (str(queue_type) in allowed) if allowed else True
            )
        except Exception:  # noqa: BLE001
            prewarm_enabled = True

        if prewarm_enabled:
            fast_mode = os.environ.get("NEUROLEAGUE_E2E_FAST") == "1"
            try:
                from neuroleague_api.clip_render import (
                    CAPTIONS_VERSION,
                    best_clip_segment,
                    captions_plan_for_segment,
                    cache_key as _cache_key,
                )
                from neuroleague_api.models import RenderJob
                from neuroleague_api.storage import ensure_artifacts_dir
                from neuroleague_api.storage_backend import get_storage_backend

                ensure_artifacts_dir()
                backend = get_storage_backend()

                start_tick, end_tick = best_clip_segment(
                    replay_for_view or {}, max_duration_sec=12.0
                )

                thumb_key = _cache_key(
                    replay_digest=replay_digest,
                    kind="thumbnail",
                    start_tick=start_tick,
                    end_tick=end_tick,
                    fps=1,
                    scale=1,
                    theme="dark",
                )
                thumb_asset_key = (
                    f"clips/thumbnails/thumb_{replay_id}_{thumb_key[:16]}.png"
                )
                try:
                    thumb_exists = backend.exists(key=thumb_asset_key)
                except Exception:  # noqa: BLE001
                    thumb_exists = False

                if not thumb_exists:
                    with SessionLocal() as session:
                        existing = (
                            session.query(RenderJob)
                            .filter(RenderJob.cache_key == thumb_key)
                            .order_by(RenderJob.created_at.desc())
                            .first()
                        )
                        if not existing or existing.status not in (
                            "queued",
                            "running",
                            "done",
                        ):
                            rj = RenderJob(
                                id=f"rj_{uuid4().hex}",
                                user_id=user_a_id,
                                kind="thumbnail",
                                target_replay_id=replay_id,
                                target_match_id=match_id,
                                params_json=orjson.dumps(
                                    {
                                        "start_tick": start_tick,
                                        "end_tick": end_tick,
                                        "scale": 1,
                                        "theme": "dark",
                                    }
                                ).decode("utf-8"),
                                cache_key=thumb_key,
                                status="queued",
                                progress=0,
                                ray_job_id=None,
                                artifact_path=None,
                                error_message=None,
                                created_at=datetime.now(UTC),
                                finished_at=None,
                            )
                            session.add(rj)
                            session.commit()

                            if fast_mode:
                                run_render_thumbnail_job(
                                    job_id=rj.id,
                                    replay_id=replay_id,
                                    start_tick=start_tick,
                                    end_tick=end_tick,
                                    scale=1,
                                    theme="dark",
                                    db_url=db_url,
                                    artifacts_dir=artifacts_dir,
                                )
                            else:
                                ref = render_thumbnail_job.remote(
                                    job_id=rj.id,
                                    replay_id=replay_id,
                                    start_tick=start_tick,
                                    end_tick=end_tick,
                                    scale=1,
                                    theme="dark",
                                    db_url=db_url,
                                    artifacts_dir=artifacts_dir,
                                )
                                rj.ray_job_id = _job_ref_hex(ref)
                                session.add(rj)
                                session.commit()

                # Best clip prewarm: vertical MP4 (9:16) with burned-in captions.
                captions_plan = captions_plan_for_segment(
                    replay_payload=replay_for_view or {},
                    start_tick=start_tick,
                    end_tick=end_tick,
                )
                best_key = _cache_key(
                    replay_digest=replay_digest,
                    kind="clip_mp4",
                    start_tick=start_tick,
                    end_tick=end_tick,
                    fps=12,
                    scale=1,
                    theme="dark",
                    aspect="9:16",
                    captions_version=captions_plan.version or CAPTIONS_VERSION,
                    captions_template_id=captions_plan.template_id,
                )
                best_asset_key = f"clips/mp4/clip_mp4_{replay_id}_{best_key[:16]}.mp4"
                try:
                    best_exists = backend.exists(key=best_asset_key)
                except Exception:  # noqa: BLE001
                    best_exists = False

                if not best_exists:
                    with SessionLocal() as session:
                        existing = (
                            session.query(RenderJob)
                            .filter(RenderJob.cache_key == best_key)
                            .order_by(RenderJob.created_at.desc())
                            .first()
                        )
                        if not existing or existing.status not in (
                            "queued",
                            "running",
                            "done",
                        ):
                            rj = RenderJob(
                                id=f"rj_{uuid4().hex}",
                                user_id=user_a_id,
                                kind="clip",
                                target_replay_id=replay_id,
                                target_match_id=match_id,
                                params_json=orjson.dumps(
                                    {
                                        "start_tick": start_tick,
                                        "end_tick": end_tick,
                                        "format": "mp4",
                                        "fps": 12,
                                        "scale": 1,
                                        "theme": "dark",
                                        "aspect": "9:16",
                                        "captions": True,
                                        "captions_version": captions_plan.version
                                        or CAPTIONS_VERSION,
                                        "captions_template_id": captions_plan.template_id,
                                        "captions_event_type": captions_plan.event_type,
                                    }
                                ).decode("utf-8"),
                                cache_key=best_key,
                                status="queued",
                                progress=0,
                                ray_job_id=None,
                                artifact_path=None,
                                error_message=None,
                                created_at=datetime.now(UTC),
                                finished_at=None,
                            )
                            session.add(rj)
                            session.commit()

                            if fast_mode:
                                run_render_clip_job(
                                    job_id=rj.id,
                                    replay_id=replay_id,
                                    start_tick=start_tick,
                                    end_tick=end_tick,
                                    format="mp4",
                                    fps=12,
                                    scale=1,
                                    theme="dark",
                                    aspect="9:16",
                                    captions=True,
                                    db_url=db_url,
                                    artifacts_dir=artifacts_dir,
                                )
                            else:
                                ref = render_clip_job.remote(
                                    job_id=rj.id,
                                    replay_id=replay_id,
                                    start_tick=start_tick,
                                    end_tick=end_tick,
                                    format="mp4",
                                    fps=12,
                                    scale=1,
                                    theme="dark",
                                    aspect="9:16",
                                    captions=True,
                                    db_url=db_url,
                                    artifacts_dir=artifacts_dir,
                                )
                                rj.ray_job_id = _job_ref_hex(ref)
                                session.add(rj)
                                session.commit()

                if fast_mode:
                    return match_id

                # Optional sharecard prewarm (v2 dark/en).
                sc_msg = f"sharecard_v2:{replay_digest}:dark:en"
                sc_key = hashlib.sha256(sc_msg.encode("utf-8")).hexdigest()
                safe_digest = replay_digest[:12] if replay_digest else "unknown"
                sc_v2_key = (
                    f"sharecards/sharecard_v2_{replay_id}_{safe_digest}_dark_en.png"
                )
                sc_v1_key = f"sharecards/sharecard_v1_{replay_id}_{safe_digest}.png"
                try:
                    sc_done = backend.exists(key=sc_v2_key) or backend.exists(
                        key=sc_v1_key
                    )
                except Exception:  # noqa: BLE001
                    sc_done = False

                if not sc_done:
                    with SessionLocal() as session:
                        existing = (
                            session.query(RenderJob)
                            .filter(RenderJob.cache_key == sc_key)
                            .order_by(RenderJob.created_at.desc())
                            .first()
                        )
                        if not existing or existing.status not in (
                            "queued",
                            "running",
                            "done",
                        ):
                            rj = RenderJob(
                                id=f"rj_{uuid4().hex}",
                                user_id=user_a_id,
                                kind="sharecard",
                                target_replay_id=replay_id,
                                target_match_id=match_id,
                                params_json=orjson.dumps(
                                    {"theme": "dark", "locale": "en"}
                                ).decode("utf-8"),
                                cache_key=sc_key,
                                status="queued",
                                progress=0,
                                ray_job_id=None,
                                artifact_path=None,
                                error_message=None,
                                created_at=datetime.now(UTC),
                                finished_at=None,
                            )
                            session.add(rj)
                            session.commit()
                            ref = render_sharecard_job.remote(
                                job_id=rj.id,
                                replay_id=replay_id,
                                theme="dark",
                                locale="en",
                                db_url=db_url,
                                artifacts_dir=artifacts_dir,
                            )
                            rj.ray_job_id = _job_ref_hex(ref)
                            session.add(rj)
                            session.commit()
            except Exception:  # noqa: BLE001
                pass

        return match_id
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            m = session.get(Match, match_id)
            if m:
                m.status = "failed"
                m.error_message = str(exc)
                m.finished_at = datetime.now(UTC)
                session.add(m)
                session.commit()
        raise


@ray.remote(max_retries=0)
def training_job(
    *, training_run_id: str, db_url: str, artifacts_dir: str, mode: str, iterations: int
) -> str:
    # Ensure workers connect to the same DB/artifacts.
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Checkpoint, TrainingRun
    from neuroleague_rl.training import build_ppo_config

    run_dir = Path(artifacts_dir) / "models" / training_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    algo = None
    try:
        cfg = build_ppo_config(mode=mode)
        algo = cfg.build_algo()

        for i in range(iterations):
            while True:
                with SessionLocal() as session:
                    tr = session.get(TrainingRun, training_run_id)
                    if not tr:
                        return "missing"
                    if tr.status == "paused":
                        pass
                    elif tr.status in ("stopped", "failed"):
                        tr.ended_at = datetime.now(UTC)
                        tr.updated_at = datetime.now(UTC)
                        session.add(tr)
                        session.commit()
                        return "stopped"
                    else:
                        tr.status = "running"
                        tr.started_at = tr.started_at or datetime.now(UTC)
                        tr.updated_at = datetime.now(UTC)
                        session.add(tr)
                        session.commit()
                        break
                time.sleep(0.5)

            result = algo.train()
            env = result.get("env_runners") or {}
            episode_return_mean = env.get("episode_return_mean", None)
            agent_returns = env.get("agent_episode_returns_mean", None)
            num_episodes = env.get("num_episodes", None)

            def _num(v: Any) -> Any:
                try:
                    if v is None:
                        return None
                    if isinstance(v, dict):
                        return {k: _num(x) for k, x in v.items()}
                    return v.item()  # numpy scalar
                except Exception:  # noqa: BLE001
                    return v

            metrics: dict[str, Any] = {
                "iteration": int(result.get("training_iteration") or (i + 1)),
                "episode_return_mean": float(_num(episode_return_mean) or 0.0),
                "agent_episode_returns_mean": _num(agent_returns) or {},
                "num_episodes": int(_num(num_episodes) or 0),
                "num_env_steps_sampled_lifetime": int(
                    _num(env.get("num_env_steps_sampled_lifetime")) or 0
                ),
            }

            checkpoint_any = algo.save(str(run_dir / f"checkpoint_{i + 1:04d}"))
            if isinstance(checkpoint_any, (str, os.PathLike)):
                checkpoint_path = str(checkpoint_any)
            elif hasattr(checkpoint_any, "path"):
                checkpoint_path = str(checkpoint_any.path)  # type: ignore[attr-defined]
            elif (
                isinstance(checkpoint_any, dict) and "checkpoint_dir" in checkpoint_any
            ):
                checkpoint_path = str(checkpoint_any["checkpoint_dir"])
            else:
                checkpoint_path = str(checkpoint_any)

            with SessionLocal() as session:
                tr = session.get(TrainingRun, training_run_id)
                if not tr:
                    return "missing"
                tr.progress = int(((i + 1) / iterations) * 100)
                tr.metrics_json = orjson.dumps(metrics).decode("utf-8")
                tr.updated_at = datetime.now(UTC)
                if tr.progress >= 100:
                    tr.status = "done"
                    tr.ended_at = datetime.now(UTC)
                session.add(tr)
                session.add(
                    Checkpoint(
                        id=f"ckpt_{training_run_id}_{i + 1:04d}",
                        training_run_id=training_run_id,
                        step=i + 1,
                        metrics_json=orjson.dumps(metrics).decode("utf-8"),
                        artifact_path=str(checkpoint_path),
                        created_at=datetime.now(UTC),
                    )
                )
                session.commit()

        return str(run_dir)
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            tr = session.get(TrainingRun, training_run_id)
            if tr:
                tr.status = "failed"
                tr.ended_at = datetime.now(UTC)
                tr.updated_at = datetime.now(UTC)
                tr.metrics_json = orjson.dumps({"error": str(exc)}).decode("utf-8")
                session.add(tr)
                session.commit()
        raise
    finally:
        if algo is not None:
            try:
                algo.stop()
            except Exception:  # noqa: BLE001
                pass


def _job_ref_hex(ref: Any) -> str | None:
    try:
        if ref is None:
            return None
        if hasattr(ref, "hex"):
            return str(ref.hex())  # type: ignore[no-any-return]
        return str(ref)
    except Exception:  # noqa: BLE001
        return None


def run_render_thumbnail_job(
    *,
    job_id: str,
    replay_id: str,
    start_tick: int,
    end_tick: int,
    scale: int,
    theme: str,
    db_url: str,
    artifacts_dir: str,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob, Replay
    from neuroleague_api.storage import (
        load_replay_json,
        resolve_local_artifact_path,
    )
    from neuroleague_api.storage_backend import get_storage_backend
    from neuroleague_api.clip_render import render_thumbnail_png_bytes

    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        if not job:
            return "missing"
        cache_key = str(job.cache_key or "")
        if job.status == "done" and job.artifact_path:
            p = resolve_local_artifact_path(job.artifact_path)
            if p is not None and p.exists():
                return job.artifact_path
            try:
                if get_storage_backend().exists(key=job.artifact_path):
                    return job.artifact_path
            except Exception:  # noqa: BLE001
                pass
        job.status = "running"
        job.progress = 5
        job.error_message = None
        session.add(job)
        session.commit()

    try:
        with SessionLocal() as session:
            replay = session.get(Replay, replay_id)
            if not replay:
                raise RuntimeError("Replay not found")
            payload = load_replay_json(artifact_path=replay.artifact_path)

        safe_prefix = (cache_key[:16] if cache_key else job_id[-12:]) or "unknown"
        asset_key = f"clips/thumbnails/thumb_{replay_id}_{safe_prefix}.png"
        backend = get_storage_backend()

        if not backend.exists(key=asset_key):
            png = render_thumbnail_png_bytes(
                replay_payload=payload,
                start_tick=int(start_tick),
                end_tick=int(end_tick),
                scale=int(scale),
                theme=str(theme),
            )
            backend.put_bytes(key=asset_key, data=png, content_type="image/png")

        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.artifact_path = asset_key
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        return asset_key
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "failed"
                job.progress = min(100, max(0, int(job.progress or 0)))
                job.error_message = str(exc)[:800]
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        raise


def run_render_clip_job(
    *,
    job_id: str,
    replay_id: str,
    start_tick: int,
    end_tick: int,
    format: str,
    fps: int,
    scale: int,
    theme: str,
    aspect: str = "16:9",
    captions: bool = False,
    db_url: str,
    artifacts_dir: str,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import RenderJob, Replay
    from neuroleague_api.storage import (
        load_replay_json,
        resolve_local_artifact_path,
    )
    from neuroleague_api.storage_backend import get_storage_backend
    from neuroleague_api.clip_render import (
        caption_lines_for_segment,
        render_gif_bytes,
        render_mp4_to_path,
        render_webm_to_path,
    )

    captions_template_id: str | None = None
    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        if not job:
            return "missing"
        try:
            params = (
                orjson.loads(job.params_json) if job.params_json else {}
            )  # type: ignore[assignment]
        except Exception:  # noqa: BLE001
            params = {}
        if isinstance(params, dict):
            raw_tpl = params.get("captions_template_id")
            captions_template_id = str(raw_tpl) if raw_tpl else None

        cache_key = str(job.cache_key or "")
        if job.status == "done" and job.artifact_path:
            p = resolve_local_artifact_path(job.artifact_path)
            if p is not None and p.exists():
                return job.artifact_path
            try:
                if get_storage_backend().exists(key=job.artifact_path):
                    return job.artifact_path
            except Exception:  # noqa: BLE001
                pass
        job.status = "running"
        job.progress = 5
        job.error_message = None
        session.add(job)
        session.commit()

    try:
        with SessionLocal() as session:
            replay = session.get(Replay, replay_id)
            if not replay:
                raise RuntimeError("Replay not found")
            payload = load_replay_json(artifact_path=replay.artifact_path)

        fmt = str(format).lower()
        if fmt not in ("gif", "webm", "mp4"):
            fmt = "webm"
        safe_prefix = (cache_key[:16] if cache_key else job_id[-12:]) or "unknown"
        asset_key = f"clips/{fmt}/clip_{fmt}_{replay_id}_{safe_prefix}.{fmt}"
        backend = get_storage_backend()
        out_path = backend.local_path(key=asset_key)

        if not backend.exists(key=asset_key):
            captions_lines = (
                caption_lines_for_segment(
                    replay_payload=payload,
                    start_tick=int(start_tick),
                    end_tick=int(end_tick),
                    template_id=captions_template_id,
                )
                if captions
                else None
            )
            if fmt == "gif":
                gif = render_gif_bytes(
                    replay_payload=payload,
                    start_tick=int(start_tick),
                    end_tick=int(end_tick),
                    fps=int(fps),
                    scale=int(scale),
                    theme=str(theme),
                    aspect=aspect,  # type: ignore[arg-type]
                    captions_lines=captions_lines,
                )
                backend.put_bytes(key=asset_key, data=gif, content_type="image/gif")
            elif fmt == "mp4":
                if out_path is not None:
                    render_mp4_to_path(
                        replay_payload=payload,
                        start_tick=int(start_tick),
                        end_tick=int(end_tick),
                        fps=int(fps),
                        scale=int(scale),
                        theme=str(theme),
                        out_path=out_path,
                        aspect=aspect,  # type: ignore[arg-type]
                        captions_lines=captions_lines,
                    )
                else:
                    from tempfile import TemporaryDirectory

                    with TemporaryDirectory(prefix="neuroleague_mp4_") as tmpdir:
                        tmp_path = Path(tmpdir) / f"clip_{replay_id}_{safe_prefix}.mp4"
                        render_mp4_to_path(
                            replay_payload=payload,
                            start_tick=int(start_tick),
                            end_tick=int(end_tick),
                            fps=int(fps),
                            scale=int(scale),
                            theme=str(theme),
                            out_path=tmp_path,
                            aspect=aspect,  # type: ignore[arg-type]
                            captions_lines=captions_lines,
                        )
                        backend.put_file(
                            key=asset_key, path=tmp_path, content_type="video/mp4"
                        )
            else:
                if out_path is not None:
                    render_webm_to_path(
                        replay_payload=payload,
                        start_tick=int(start_tick),
                        end_tick=int(end_tick),
                        fps=int(fps),
                        scale=int(scale),
                        theme=str(theme),
                        out_path=out_path,
                        aspect=aspect,  # type: ignore[arg-type]
                        captions_lines=captions_lines,
                    )
                else:
                    from tempfile import TemporaryDirectory

                    with TemporaryDirectory(prefix="neuroleague_webm_") as tmpdir:
                        tmp_path = Path(tmpdir) / f"clip_{replay_id}_{safe_prefix}.webm"
                        render_webm_to_path(
                            replay_payload=payload,
                            start_tick=int(start_tick),
                            end_tick=int(end_tick),
                            fps=int(fps),
                            scale=int(scale),
                            theme=str(theme),
                            out_path=tmp_path,
                            aspect=aspect,  # type: ignore[arg-type]
                            captions_lines=captions_lines,
                        )
                        backend.put_file(
                            key=asset_key, path=tmp_path, content_type="video/webm"
                        )

        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.artifact_path = asset_key
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        return asset_key
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "failed"
                job.progress = min(100, max(0, int(job.progress or 0)))
                job.error_message = str(exc)[:800]
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        raise


def run_render_sharecard_job(
    *,
    job_id: str,
    replay_id: str,
    theme: str,
    locale: str,
    db_url: str,
    artifacts_dir: str,
) -> str:
    os.environ["NEUROLEAGUE_DB_URL"] = db_url
    os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = artifacts_dir
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Match, RenderJob, Replay
    from neuroleague_api.storage import (
        load_replay_json,
        resolve_local_artifact_path,
    )
    from neuroleague_api.storage_backend import get_storage_backend
    from neuroleague_api.routers.replays import (
        _render_sharecard_png_v1,
        _render_sharecard_png_v2,
        _sharecard_html_v2,
    )

    with SessionLocal() as session:
        job = session.get(RenderJob, job_id)
        if not job:
            return "missing"
        if job.status == "done" and job.artifact_path:
            p = resolve_local_artifact_path(job.artifact_path)
            if p is not None and p.exists():
                return job.artifact_path
            try:
                if get_storage_backend().exists(key=job.artifact_path):
                    return job.artifact_path
            except Exception:  # noqa: BLE001
                pass
        job.status = "running"
        job.progress = 5
        job.error_message = None
        session.add(job)
        session.commit()

    try:
        with SessionLocal() as session:
            replay = session.get(Replay, replay_id)
            if not replay:
                raise RuntimeError("Replay not found")
            match = session.get(Match, replay.match_id)
            if not match:
                raise RuntimeError("Match not found")
            payload = load_replay_json(artifact_path=replay.artifact_path)
            digest = str(replay.digest or payload.get("digest") or "")
            safe_digest = digest[:12] if digest else "unknown"

        key_v2 = (
            f"sharecards/sharecard_v2_{replay_id}_{safe_digest}_{theme}_{locale}.png"
        )
        key_v1 = f"sharecards/sharecard_v1_{replay_id}_{safe_digest}.png"
        backend = get_storage_backend()

        force_v1 = os.environ.get("NEUROLEAGUE_E2E_FAST") == "1"
        if force_v1:
            if not backend.exists(key=key_v1):
                backend.put_bytes(
                    key=key_v1,
                    data=_render_sharecard_png_v1(replay_payload=payload, match=match),
                    content_type="image/png",
                )
            chosen_key = key_v1
        else:
            if not backend.exists(key=key_v2):
                html = _sharecard_html_v2(
                    replay_payload=payload, match=match, theme=theme, locale=locale
                )
                try:
                    local = backend.local_path(key=key_v2)
                    if local is not None:
                        _render_sharecard_png_v2(html=html, out_path=local)
                    else:
                        from tempfile import TemporaryDirectory

                        with TemporaryDirectory(
                            prefix="neuroleague_sharecard_"
                        ) as tmpdir:
                            tmp_path = (
                                Path(tmpdir)
                                / f"sharecard_v2_{replay_id}_{safe_digest}.png"
                            )
                            _render_sharecard_png_v2(html=html, out_path=tmp_path)
                            backend.put_file(
                                key=key_v2, path=tmp_path, content_type="image/png"
                            )
                except Exception:  # noqa: BLE001
                    if not backend.exists(key=key_v1):
                        backend.put_bytes(
                            key=key_v1,
                            data=_render_sharecard_png_v1(
                                replay_payload=payload, match=match
                            ),
                            content_type="image/png",
                        )
                    chosen_key = key_v1
                else:
                    chosen_key = key_v2
            else:
                chosen_key = key_v2

        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "done"
                job.progress = 100
                job.artifact_path = chosen_key
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        return chosen_key
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as session:
            job = session.get(RenderJob, job_id)
            if job:
                job.status = "failed"
                job.progress = min(100, max(0, int(job.progress or 0)))
                job.error_message = str(exc)[:800]
                job.finished_at = datetime.now(UTC)
                session.add(job)
                session.commit()
        raise


@ray.remote(max_retries=0)
def render_thumbnail_job(**kwargs: Any) -> str:
    return run_render_thumbnail_job(**kwargs)


@ray.remote(max_retries=0)
def render_clip_job(**kwargs: Any) -> str:
    return run_render_clip_job(**kwargs)


@ray.remote(max_retries=0)
def render_sharecard_job(**kwargs: Any) -> str:
    return run_render_sharecard_job(**kwargs)
