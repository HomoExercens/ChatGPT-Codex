from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest


_TEST_ROOT = Path(tempfile.mkdtemp(prefix="neuroleague_test_"))
_DB_PATH = _TEST_ROOT / "neuroleague_test.db"
_ARTIFACTS_DIR = _TEST_ROOT / "artifacts"

os.environ["NEUROLEAGUE_DB_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["NEUROLEAGUE_ARTIFACTS_DIR"] = str(_ARTIFACTS_DIR)
os.environ["NEUROLEAGUE_AUTH_JWT_SECRET"] = "test-secret"
os.environ["CUDA_VISIBLE_DEVICES"] = ""


@pytest.fixture(scope="session")
def seeded_db() -> None:
    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import Base, SessionLocal, engine
    from neuroleague_api.elo import update_elo
    from neuroleague_api.models import Blueprint, Match, Rating, Replay, User, Wallet
    from neuroleague_api.storage import save_replay_json
    from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
    from neuroleague_sim.models import BlueprintSpec
    from neuroleague_sim.simulate import simulate_match

    Base.metadata.create_all(engine)
    settings = Settings()

    now = datetime.now(UTC)
    demo_id = "user_demo"
    bot_id = "bot_alpha"

    with SessionLocal() as session:
        if session.get(User, demo_id):
            return

        demo = User(
            id=demo_id,
            username="demo",
            display_name="Dr. Kairos",
            is_guest=False,
            created_at=now,
        )
        bot = User(
            id=bot_id,
            username=None,
            display_name="Lab_Alpha",
            is_guest=True,
            created_at=now,
        )
        session.add(demo)
        session.add(bot)
        session.add(Wallet(user_id=demo.id, tokens_balance=14_500))
        session.add(Wallet(user_id=bot.id, tokens_balance=0))

        rating_a = Rating(
            user_id=demo.id, mode="1v1", elo=1000, games_played=0, updated_at=now
        )
        rating_b = Rating(
            user_id=bot.id, mode="1v1", elo=1000, games_played=0, updated_at=now
        )
        session.add(rating_a)
        session.add(rating_b)
        session.add(
            Rating(
                user_id=demo.id, mode="team", elo=1000, games_played=0, updated_at=now
            )
        )
        session.add(
            Rating(
                user_id=bot.id, mode="team", elo=1000, games_played=0, updated_at=now
            )
        )

        spec_a = BlueprintSpec(
            mode="1v1",
            team=[
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
        )
        spec_b = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "ember_fox",
                    "formation": "front",
                    "items": {"weapon": "ember_blade", "armor": None, "utility": None},
                }
            ],
        )

        bp_a = Blueprint(
            id="bp_demo_1v1",
            user_id=demo.id,
            name="Mech Counter V1",
            mode="1v1",
            ruleset_version=settings.ruleset_version,
            status="submitted",
            spec_json=canonical_json_bytes(spec_a.model_dump()).decode("utf-8"),
            spec_hash=canonical_sha256(spec_a.model_dump()),
            created_at=now,
            updated_at=now,
        )
        bp_b = Blueprint(
            id="bp_bot_1v1",
            user_id=bot.id,
            name="Bot: Ember Rush",
            mode="1v1",
            ruleset_version=settings.ruleset_version,
            status="submitted",
            spec_json=canonical_json_bytes(spec_b.model_dump()).decode("utf-8"),
            spec_hash=canonical_sha256(spec_b.model_dump()),
            created_at=now,
            updated_at=now,
        )
        session.add(bp_a)
        session.add(bp_b)

        match_id = "m_test_seed"
        replay_id = "r_test_seed"
        replay = simulate_match(
            match_id=match_id, seed_index=0, blueprint_a=spec_a, blueprint_b=spec_b
        )
        artifact_path = save_replay_json(
            replay_id=replay_id, payload=replay.model_dump()
        )

        score_a = (
            1.0
            if replay.end_summary.winner == "A"
            else 0.0
            if replay.end_summary.winner == "B"
            else 0.5
        )
        elo = update_elo(
            rating_a=rating_a.elo,
            rating_b=rating_b.elo,
            score_a=score_a,
            games_played_a=rating_a.games_played,
            games_played_b=rating_b.games_played,
        )
        rating_a.elo = elo.new_a
        rating_a.games_played += 1
        rating_a.updated_at = now

        rating_b.elo = elo.new_b
        rating_b.games_played += 1
        rating_b.updated_at = now

        session.add(
            Match(
                id=match_id,
                mode="1v1",
                ruleset_version=settings.ruleset_version,
                seed_set_count=1,
                user_a_id=demo.id,
                user_b_id=bot.id,
                blueprint_a_id=bp_a.id,
                blueprint_b_id=bp_b.id,
                result=replay.end_summary.winner,
                elo_delta_a=elo.delta_a,
                elo_delta_b=elo.delta_b,
                created_at=now,
                finished_at=now,
            )
        )
        session.add(
            Replay(
                id=replay_id,
                match_id=match_id,
                artifact_path=artifact_path,
                digest=replay.digest,
                created_at=now,
            )
        )
        session.add(rating_a)
        session.add(rating_b)
        session.commit()


@pytest.fixture()
def api_client(seeded_db):
    from fastapi.testclient import TestClient

    from neuroleague_api.main import app

    return TestClient(app)
