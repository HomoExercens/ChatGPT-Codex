from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import orjson
from sqlalchemy import delete, select

from neuroleague_api.core.config import Settings
from neuroleague_api.db import SessionLocal
from neuroleague_api.build_code import encode_build_code
from neuroleague_api.elo import update_elo
from neuroleague_api.experiments import ensure_default_experiments
from neuroleague_api.models import (
    ABAssignment,
    Blueprint,
    Challenge,
    ChallengeAttempt,
    Cosmetic,
    DiscordOutbox,
    Event,
    FeaturedItem,
    FunnelDaily,
    Match,
    MetricsDaily,
    Quest,
    QuestAssignment,
    QuestEventApplied,
    Rating,
    Replay,
    User,
    UserCosmetic,
    Wallet,
)
from neuroleague_api.storage import save_replay_json
from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.simulate import simulate_match


DEMO_USER_ID = "user_demo"

BOT_USERS = [
    ("bot_mech", "Lab_Mech"),
    ("bot_ember", "Lab_Ember"),
    ("bot_vine", "Lab_Vine"),
    ("bot_mist", "Lab_Mist"),
    ("bot_slime", "Lab_Slime"),
    ("bot_crit", "Lab_Crit"),
]

LAB_USERS = [
    ("user_alice", "alice", "Alice Vector", 1032),
    ("user_bob", "bob", "Bob Forge", 990),
    ("user_carol", "carol", "Carol Mist", 1014),
    ("user_dave", "dave", "Dave Void", 1048),
    ("user_eve", "eve", "Eve Vine", 978),
    ("user_frank", "frank", "Frank Sun", 1006),
]

SEED_BLUEPRINT_IDS = [
    "bp_demo_1v1",
    "bp_demo_storm_1v1",
    "bp_demo_void_1v1",
    "bp_demo_vine_1v1",
    "bp_demo_sun_1v1",
    "bp_demo_team_mechline",
    "bp_demo_team_mysticcircle",
    "bp_demo_team_beastpack",
    "bp_bot_mech_1v1",
    "bp_bot_ember_1v1",
    "bp_bot_vine_1v1",
    "bp_bot_mist_1v1",
    "bp_bot_slime_1v1",
    "bp_bot_crit_1v1",
    "bp_bot_mech_team",
    "bp_bot_vine_team",
    "bp_bot_mist_team",
    "bp_bot_slime_team",
    "bp_bot_crit_team",
    "bp_bot_burst_team",
    "bp_lab_alice_1v1",
    "bp_lab_alice_team",
    "bp_lab_bob_1v1",
    "bp_lab_bob_team",
    "bp_lab_carol_1v1",
    "bp_lab_carol_team",
    "bp_lab_dave_1v1",
    "bp_lab_dave_team",
    "bp_lab_eve_1v1",
    "bp_lab_eve_team",
    "bp_lab_frank_1v1",
    "bp_lab_frank_team",
]

SEED_MATCH_IDS = [f"m_seed_{i:03d}" for i in range(1, 21)]
SEED_REPLAY_IDS = [f"r_seed_{i:03d}" for i in range(1, 21)]


def _ensure_user(
    session,
    *,
    user_id: str,
    username: str | None,
    display_name: str,
    is_guest: bool,
    tokens: int,
) -> None:
    now = datetime.now(UTC)
    user = session.get(User, user_id)
    if not user:
        user = User(
            id=user_id,
            username=username,
            display_name=display_name,
            is_guest=is_guest,
            created_at=now,
        )
        session.add(user)
    else:
        user.display_name = display_name
        user.is_guest = is_guest
        if username is not None:
            user.username = username

    wallet = session.get(Wallet, user_id)
    if not wallet:
        session.add(Wallet(user_id=user_id, tokens_balance=tokens))
    else:
        wallet.tokens_balance = tokens


def _ensure_rating(
    session, user_id: str, mode: str, elo: int, games: int, *, overwrite: bool
) -> None:
    rating = session.get(Rating, {"user_id": user_id, "mode": mode})
    if rating:
        if overwrite:
            rating.elo = elo
            rating.games_played = games
            rating.updated_at = datetime.now(UTC)
            session.add(rating)
        return
    session.add(
        Rating(
            user_id=user_id,
            mode=mode,
            elo=elo,
            games_played=games,
            updated_at=datetime.now(UTC),
        )
    )


def _ensure_blueprint(
    session,
    *,
    blueprint_id: str,
    user_id: str,
    name: str,
    mode: str,
    status: str,
    ruleset_version: str,
    spec: BlueprintSpec,
) -> None:
    now = datetime.now(UTC)
    spec_json = canonical_json_bytes(spec.model_dump()).decode("utf-8")
    spec_hash = canonical_sha256(spec.model_dump())
    build_code: str | None
    try:
        build_code = encode_build_code(spec=spec)
    except Exception:  # noqa: BLE001
        build_code = None
    bp = session.get(Blueprint, blueprint_id)
    if not bp:
        bp = Blueprint(
            id=blueprint_id,
            user_id=user_id,
            name=name,
            mode=mode,
            ruleset_version=ruleset_version,
            status=status,
            spec_json=spec_json,
            spec_hash=spec_hash,
            meta_json="{}",
            build_code=build_code,
            submitted_at=now if status == "submitted" else None,
            created_at=now,
            updated_at=now,
        )
        session.add(bp)
        return
    bp.name = name
    bp.mode = mode
    bp.ruleset_version = ruleset_version
    bp.status = status
    bp.spec_json = spec_json
    bp.spec_hash = spec_hash
    bp.updated_at = now
    if not bp.build_code and build_code:
        bp.build_code = build_code
    if status == "submitted" and bp.submitted_at is None:
        bp.submitted_at = now
    if status != "submitted":
        bp.submitted_at = None
    session.add(bp)


def _winner_to_score_a(winner: str) -> float:
    if winner == "A":
        return 1.0
    if winner == "B":
        return 0.0
    return 0.5


def _ensure_match_and_replay(
    session,
    *,
    match_id: str,
    replay_id: str,
    ruleset_version: str,
    mode: str,
    seed_set_count: int,
    user_a_id: str,
    user_b_id: str,
    blueprint_a_id: str,
    blueprint_b_id: str,
    spec_a: BlueprintSpec,
    spec_b: BlueprintSpec,
    created_at: datetime,
) -> None:
    from neuroleague_sim.modifiers import select_match_modifiers

    modifiers = select_match_modifiers(match_id)
    replay = simulate_match(
        match_id=match_id,
        seed_index=0,
        blueprint_a=spec_a,
        blueprint_b=spec_b,
        modifiers=modifiers,
    )
    artifact_path = save_replay_json(replay_id=replay_id, payload=replay.model_dump())

    rating_a = session.get(Rating, {"user_id": user_a_id, "mode": mode})
    rating_b = session.get(Rating, {"user_id": user_b_id, "mode": mode})
    if not rating_a or not rating_b:
        raise RuntimeError("Missing ratings for seeded match")

    elo = update_elo(
        rating_a=rating_a.elo,
        rating_b=rating_b.elo,
        score_a=_winner_to_score_a(replay.end_summary.winner),
        games_played_a=rating_a.games_played,
        games_played_b=rating_b.games_played,
    )
    rating_a.elo = elo.new_a
    rating_a.games_played += 1
    rating_a.updated_at = created_at

    rating_b.elo = elo.new_b
    rating_b.games_played += 1
    rating_b.updated_at = created_at

    m = session.get(Match, match_id)
    if not m:
        m = Match(
            id=match_id,
            mode=mode,
            ruleset_version=ruleset_version,
            portal_id=str(modifiers.get("portal_id") or ""),
            augments_a_json=orjson.dumps(modifiers.get("augments_a") or []).decode(
                "utf-8"
            ),
            augments_b_json=orjson.dumps(modifiers.get("augments_b") or []).decode(
                "utf-8"
            ),
            seed_set_count=seed_set_count,
            user_a_id=user_a_id,
            user_b_id=user_b_id,
            blueprint_a_id=blueprint_a_id,
            blueprint_b_id=blueprint_b_id,
            result=replay.end_summary.winner,
            elo_delta_a=elo.delta_a,
            elo_delta_b=elo.delta_b,
            created_at=created_at,
            finished_at=created_at,
        )
        session.add(m)
    else:
        m.mode = mode
        m.ruleset_version = ruleset_version
        m.portal_id = str(modifiers.get("portal_id") or "")
        m.augments_a_json = orjson.dumps(modifiers.get("augments_a") or []).decode(
            "utf-8"
        )
        m.augments_b_json = orjson.dumps(modifiers.get("augments_b") or []).decode(
            "utf-8"
        )
        m.seed_set_count = seed_set_count
        m.user_a_id = user_a_id
        m.user_b_id = user_b_id
        m.blueprint_a_id = blueprint_a_id
        m.blueprint_b_id = blueprint_b_id
        m.result = replay.end_summary.winner
        m.elo_delta_a = elo.delta_a
        m.elo_delta_b = elo.delta_b
        m.created_at = created_at
        m.finished_at = created_at
        session.add(m)

    replay_row = session.get(Replay, replay_id)
    if not replay_row:
        replay_row = session.scalar(select(Replay).where(Replay.match_id == match_id))
    if replay_row and replay_row.id != replay_id:
        session.delete(replay_row)
        replay_row = None
    if not replay_row:
        session.add(
            Replay(
                id=replay_id,
                match_id=match_id,
                artifact_path=artifact_path,
                digest=replay.digest,
                created_at=created_at,
            )
        )
    else:
        replay_row.match_id = match_id
        replay_row.artifact_path = artifact_path
        replay_row.digest = replay.digest
        replay_row.created_at = created_at
        session.add(replay_row)

    session.add(rating_a)
    session.add(rating_b)


def _ensure_cosmetic(
    session, *, cosmetic_id: str, name: str, kind: str = "badge"
) -> None:
    now = datetime.now(UTC)
    row = session.get(Cosmetic, cosmetic_id)
    if row:
        row.name = name
        row.kind = kind
        session.add(row)
        return
    session.add(
        Cosmetic(
            id=cosmetic_id,
            kind=kind,
            name=name,
            asset_path=None,
            created_at=now,
        )
    )


def _ensure_quest(
    session,
    *,
    cadence: str,
    key: str,
    title: str,
    description: str,
    goal_count: int,
    event_type: str,
    reward_cosmetic_id: str,
    reward_amount: int = 1,
    filters: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC)
    row = session.scalar(
        select(Quest).where(Quest.cadence == str(cadence)).where(Quest.key == str(key))
    )
    filters_json = orjson.dumps(filters or {}).decode("utf-8")
    if row:
        row.title = title
        row.description = description
        row.goal_count = int(goal_count)
        row.event_type = str(event_type)
        row.filters_json = filters_json
        row.reward_cosmetic_id = str(reward_cosmetic_id)
        row.reward_amount = int(reward_amount)
        session.add(row)
        return
    session.add(
        Quest(
            id=f"q_{uuid4().hex}",
            cadence=str(cadence),
            key=str(key),
            title=str(title),
            description=str(description),
            goal_count=int(goal_count),
            event_type=str(event_type),
            filters_json=filters_json,
            reward_cosmetic_id=str(reward_cosmetic_id),
            reward_amount=int(reward_amount),
            active_from=None,
            active_to=None,
            created_at=now,
        )
    )


def _ensure_featured(
    session,
    *,
    kind: str,
    target_id: str,
    priority: int,
    title_override: str | None = None,
) -> None:
    now = datetime.now(UTC)
    existing = session.scalar(
        select(FeaturedItem)
        .where(FeaturedItem.kind == str(kind))
        .where(FeaturedItem.target_id == str(target_id))
        .where(FeaturedItem.status == "active")
        .order_by(FeaturedItem.created_at.desc())
        .limit(1)
    )
    if existing:
        existing.priority = int(priority)
        existing.title_override = title_override
        session.add(existing)
        return
    session.add(
        FeaturedItem(
            id=f"fi_{uuid4().hex}",
            kind=str(kind),
            target_id=str(target_id),
            title_override=title_override,
            priority=int(priority),
            starts_at=None,
            ends_at=None,
            status="active",
            created_at=now,
            created_by="seed",
        )
    )


def main() -> None:
    settings = Settings()
    os.makedirs(settings.artifacts_dir, exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset", action="store_true", help="Delete seeded rows and regenerate."
    )
    args = parser.parse_args()

    artifacts_dir = Path(settings.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _delete_replay_artifact(path: str) -> None:
        from neuroleague_api.storage import resolve_local_artifact_path

        try:
            p = resolve_local_artifact_path(path)
            if p is None:
                return
            p.unlink(missing_ok=True)
        except Exception:
            pass

    with SessionLocal() as session:
        ensure_default_experiments(session)
        if args.reset:
            session.execute(delete(ABAssignment))
            session.execute(delete(Event))
            session.execute(delete(MetricsDaily))
            session.execute(delete(FunnelDaily))
            session.execute(delete(QuestEventApplied))
            session.execute(delete(QuestAssignment))
            session.execute(delete(ChallengeAttempt))
            session.execute(delete(Challenge))
            session.execute(delete(DiscordOutbox))
            session.execute(
                delete(FeaturedItem).where(FeaturedItem.created_by == "seed")
            )
            session.execute(
                delete(UserCosmetic).where(
                    UserCosmetic.cosmetic_id.like("badge_quest_%")
                )
            )
            session.execute(delete(Cosmetic).where(Cosmetic.id.like("badge_quest_%")))
            for row in session.scalars(
                select(Replay).where(Replay.id.like("r_seed_%"))
            ).all():
                _delete_replay_artifact(row.artifact_path)
                session.delete(row)
            for row in session.scalars(
                select(Match).where(Match.id.like("m_seed_%"))
            ).all():
                session.delete(row)
            for bid in SEED_BLUEPRINT_IDS:
                row = session.get(Blueprint, bid)
                if row:
                    session.delete(row)
            for bot_id, _ in BOT_USERS:
                row = session.get(User, bot_id)
                if row:
                    session.delete(row)
            for lab_user_id, _, _, _ in LAB_USERS:
                row = session.get(User, lab_user_id)
                if row:
                    session.delete(row)
            demo_row = session.get(User, DEMO_USER_ID)
            if demo_row:
                session.delete(demo_row)
            session.commit()

        _ensure_user(
            session,
            user_id=DEMO_USER_ID,
            username="demo",
            display_name="Dr. Kairos",
            is_guest=False,
            tokens=14_500,
        )
        for bot_id, bot_name in BOT_USERS:
            _ensure_user(
                session,
                user_id=bot_id,
                username=None,
                display_name=bot_name,
                is_guest=True,
                tokens=0,
            )
        for lab_user_id, username, display_name, _ in LAB_USERS:
            _ensure_user(
                session,
                user_id=lab_user_id,
                username=username,
                display_name=display_name,
                is_guest=False,
                tokens=0,
            )

        has_any_demo_match = (
            session.scalar(
                select(Match.id).where(Match.user_a_id == DEMO_USER_ID).limit(1)
            )
            is not None
        )
        should_seed_matches = args.reset or not has_any_demo_match

        # Initialize ratings for demo/bots. Only overwrite on reset / first seed.
        _ensure_rating(
            session,
            DEMO_USER_ID,
            "1v1",
            1000,
            0,
            overwrite=should_seed_matches,
        )
        _ensure_rating(
            session,
            DEMO_USER_ID,
            "team",
            1000,
            0,
            overwrite=should_seed_matches,
        )
        for bot_id, _ in BOT_USERS:
            _ensure_rating(
                session,
                bot_id,
                "1v1",
                1000,
                0,
                overwrite=should_seed_matches,
            )
            _ensure_rating(
                session,
                bot_id,
                "team",
                1000,
                0,
                overwrite=should_seed_matches,
            )
        for lab_user_id, _, _, elo in LAB_USERS:
            _ensure_rating(
                session,
                lab_user_id,
                "1v1",
                elo,
                50,
                overwrite=should_seed_matches,
            )
            _ensure_rating(
                session,
                lab_user_id,
                "team",
                elo,
                50,
                overwrite=should_seed_matches,
            )
        session.commit()

        # Blueprints
        demo_1v1 = BlueprintSpec(
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
        demo_storm = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "storm_hawk",
                    "formation": "front",
                    "items": {
                        "weapon": "ion_repeater",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                }
            ],
        )
        demo_void = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "void_wisp",
                    "formation": "front",
                    "items": {
                        "weapon": "void_dagger",
                        "armor": None,
                        "utility": "targeting_array",
                    },
                }
            ],
        )
        demo_vine = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "thornback_boar",
                    "formation": "front",
                    "items": {
                        "weapon": "thorn_spear",
                        "armor": "thorn_mail",
                        "utility": "smoke_emitter",
                    },
                }
            ],
        )
        demo_sun = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "sun_paladin",
                    "formation": "front",
                    "items": {
                        "weapon": "ember_blade",
                        "armor": "reinforced_plate",
                        "utility": "phoenix_ash",
                    },
                }
            ],
        )
        demo_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "coolant_shell",
                        "utility": "clockwork_core",
                    },
                },
                {
                    "creature_id": "iron_striker",
                    "formation": "front",
                    "items": {"weapon": "ion_repeater", "armor": None, "utility": None},
                },
                {
                    "creature_id": "scrap_artificer",
                    "formation": "back",
                    "items": {
                        "weapon": None,
                        "armor": None,
                        "utility": "healing_drones",
                    },
                },
            ],
        )
        demo_team_mystic = BlueprintSpec(
            mode="team",
            team=[
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
                    "items": {"weapon": None, "armor": None, "utility": "phoenix_ash"},
                },
            ],
        )
        demo_team_beast = BlueprintSpec(
            mode="team",
            team=[
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
        )

        bot_mech = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {
                        "weapon": "plasma_lance",
                        "armor": "coolant_shell",
                        "utility": "clockwork_core",
                    },
                }
            ],
        )
        bot_ember = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "ember_fox",
                    "formation": "front",
                    "items": {
                        "weapon": "ember_blade",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                }
            ],
        )
        bot_vine = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "thornback_boar",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "thorn_mail",
                        "utility": "smoke_emitter",
                    },
                }
            ],
        )
        bot_mist = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "mist_sage",
                    "formation": "front",
                    "items": {
                        "weapon": "crystal_staff",
                        "armor": "medic_vest",
                        "utility": "healing_drones",
                    },
                }
            ],
        )
        bot_slime = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "slime_knight",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "reinforced_plate",
                        "utility": "phoenix_ash",
                    },
                }
            ],
        )
        bot_crit = BlueprintSpec(
            mode="1v1",
            team=[
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
        )
        bot_mech_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "coolant_shell",
                        "utility": "mech_sigil",
                    },
                },
                {
                    "creature_id": "iron_striker",
                    "formation": "front",
                    "items": {
                        "weapon": "plasma_lance",
                        "armor": "reinforced_plate",
                        "utility": "mech_sigil",
                    },
                },
                {
                    "creature_id": "scrap_artificer",
                    "formation": "back",
                    "items": {"weapon": None, "armor": None, "utility": "mech_sigil"},
                },
            ],
        )
        bot_vine_team = BlueprintSpec(
            mode="team",
            team=[
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
                    "items": {"weapon": "ember_blade", "armor": None, "utility": None},
                },
            ],
        )
        bot_mist_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "mist_sage",
                    "formation": "front",
                    "items": {
                        "weapon": "crystal_staff",
                        "armor": "medic_vest",
                        "utility": "mystic_sigil",
                    },
                },
                {
                    "creature_id": "crystal_weaver",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "runic_barrier",
                        "utility": "targeting_array",
                    },
                },
                {
                    "creature_id": "field_medic",
                    "formation": "back",
                    "items": {"weapon": None, "armor": None, "utility": "phoenix_ash"},
                },
            ],
        )
        bot_slime_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "slime_knight",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "reinforced_plate",
                        "utility": "knight_sigil",
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
        )
        bot_crit_team = BlueprintSpec(
            mode="team",
            team=[
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
                        "weapon": "crystal_staff",
                        "armor": None,
                        "utility": None,
                    },
                },
                {
                    "creature_id": "ember_fox",
                    "formation": "back",
                    "items": {
                        "weapon": "ember_blade",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                },
            ],
        )
        bot_burst_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "ember_fox",
                    "formation": "front",
                    "items": {
                        "weapon": "ember_blade",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                },
                {
                    "creature_id": "storm_hawk",
                    "formation": "front",
                    "items": {"weapon": "ion_repeater", "armor": None, "utility": None},
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
        )

        # Lab-user pool (non-bot) for PvP matchmaking demos.
        lab_alice_1v1 = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "storm_hawk",
                    "formation": "front",
                    "items": {
                        "weapon": "ion_repeater",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                }
            ],
        )
        lab_alice_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "storm_hawk",
                    "formation": "front",
                    "items": {"weapon": "ion_repeater", "armor": None, "utility": None},
                },
                {
                    "creature_id": "ember_fox",
                    "formation": "front",
                    "items": {
                        "weapon": "ember_blade",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                },
                {
                    "creature_id": "field_medic",
                    "formation": "back",
                    "items": {
                        "weapon": None,
                        "armor": "medic_vest",
                        "utility": "healing_drones",
                    },
                },
            ],
        )
        lab_bob_1v1 = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {
                        "weapon": "plasma_lance",
                        "armor": "coolant_shell",
                        "utility": "clockwork_core",
                    },
                }
            ],
        )
        lab_bob_team = BlueprintSpec(
            mode="team",
            team=[
                {
                    "creature_id": "clockwork_golem",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "coolant_shell",
                        "utility": "mech_sigil",
                    },
                },
                {
                    "creature_id": "iron_striker",
                    "formation": "front",
                    "items": {"weapon": "plasma_lance", "armor": None, "utility": None},
                },
                {
                    "creature_id": "scrap_artificer",
                    "formation": "back",
                    "items": {
                        "weapon": None,
                        "armor": None,
                        "utility": "healing_drones",
                    },
                },
            ],
        )
        lab_carol_1v1 = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "mist_sage",
                    "formation": "front",
                    "items": {
                        "weapon": "crystal_staff",
                        "armor": "medic_vest",
                        "utility": "healing_drones",
                    },
                }
            ],
        )
        lab_carol_team = BlueprintSpec(
            mode="team",
            team=[
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
                        "utility": "mystic_sigil",
                    },
                },
                {
                    "creature_id": "field_medic",
                    "formation": "back",
                    "items": {"weapon": None, "armor": None, "utility": "phoenix_ash"},
                },
            ],
        )
        lab_dave_1v1 = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "void_wisp",
                    "formation": "front",
                    "items": {
                        "weapon": "void_dagger",
                        "armor": None,
                        "utility": "targeting_array",
                    },
                }
            ],
        )
        lab_dave_team = BlueprintSpec(
            mode="team",
            team=[
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
                    "creature_id": "ember_fox",
                    "formation": "front",
                    "items": {"weapon": "ember_blade", "armor": None, "utility": None},
                },
                {
                    "creature_id": "storm_hawk",
                    "formation": "back",
                    "items": {
                        "weapon": "ion_repeater",
                        "armor": None,
                        "utility": "adrenaline_module",
                    },
                },
            ],
        )
        lab_eve_1v1 = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "thornback_boar",
                    "formation": "front",
                    "items": {
                        "weapon": "thorn_spear",
                        "armor": "thorn_mail",
                        "utility": "smoke_emitter",
                    },
                }
            ],
        )
        lab_eve_team = BlueprintSpec(
            mode="team",
            team=[
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
                    "creature_id": "slime_knight",
                    "formation": "front",
                    "items": {
                        "weapon": None,
                        "armor": "reinforced_plate",
                        "utility": None,
                    },
                },
                {
                    "creature_id": "storm_hawk",
                    "formation": "back",
                    "items": {"weapon": "ion_repeater", "armor": None, "utility": None},
                },
            ],
        )
        lab_frank_1v1 = BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "sun_paladin",
                    "formation": "front",
                    "items": {
                        "weapon": "ember_blade",
                        "armor": "reinforced_plate",
                        "utility": "phoenix_ash",
                    },
                }
            ],
        )
        lab_frank_team = BlueprintSpec(
            mode="team",
            team=[
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
                    "creature_id": "field_medic",
                    "formation": "back",
                    "items": {
                        "weapon": None,
                        "armor": "medic_vest",
                        "utility": "healing_drones",
                    },
                },
            ],
        )

        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_1v1",
            user_id=DEMO_USER_ID,
            name="Mech Counter V1",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=demo_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_storm_1v1",
            user_id=DEMO_USER_ID,
            name="Storm Blitz",
            mode="1v1",
            status="draft",
            ruleset_version=settings.ruleset_version,
            spec=demo_storm,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_void_1v1",
            user_id=DEMO_USER_ID,
            name="Void Glasscannon",
            mode="1v1",
            status="draft",
            ruleset_version=settings.ruleset_version,
            spec=demo_void,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_vine_1v1",
            user_id=DEMO_USER_ID,
            name="Vine Fortress",
            mode="1v1",
            status="draft",
            ruleset_version=settings.ruleset_version,
            spec=demo_vine,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_sun_1v1",
            user_id=DEMO_USER_ID,
            name="Sun Vanguard",
            mode="1v1",
            status="draft",
            ruleset_version=settings.ruleset_version,
            spec=demo_sun,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_team_mechline",
            user_id=DEMO_USER_ID,
            name="Team: Mechline",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=demo_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_team_mysticcircle",
            user_id=DEMO_USER_ID,
            name="Team: Mystic Circle",
            mode="team",
            status="draft",
            ruleset_version=settings.ruleset_version,
            spec=demo_team_mystic,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_demo_team_beastpack",
            user_id=DEMO_USER_ID,
            name="Team: Beast Pack",
            mode="team",
            status="draft",
            ruleset_version=settings.ruleset_version,
            spec=demo_team_beast,
        )

        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_mech_1v1",
            user_id="bot_mech",
            name="Bot: Mech Counter",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_mech,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_ember_1v1",
            user_id="bot_ember",
            name="Bot: Ember Rush",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_ember,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_vine_1v1",
            user_id="bot_vine",
            name="Bot: Vine Wall",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_vine,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_mist_1v1",
            user_id="bot_mist",
            name="Bot: Mist Sustain",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_mist,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_slime_1v1",
            user_id="bot_slime",
            name="Bot: Slime Baseline",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_slime,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_crit_1v1",
            user_id="bot_crit",
            name="Bot: Crit Gamble",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_crit,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_mech_team",
            user_id="bot_mech",
            name="Bot: Mech Cannon",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_mech_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_vine_team",
            user_id="bot_vine",
            name="Bot: Beast Stampede",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_vine_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_mist_team",
            user_id="bot_mist",
            name="Bot: Mystic Sustain",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_mist_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_slime_team",
            user_id="bot_slime",
            name="Bot: Knight Brigade",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_slime_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_crit_team",
            user_id="bot_crit",
            name="Bot: Void Spike",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_crit_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_bot_burst_team",
            user_id="bot_ember",
            name="Bot: Burst Trio",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=bot_burst_team,
        )

        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_alice_1v1",
            user_id="user_alice",
            name="Alice: Storm Tempo",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_alice_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_alice_team",
            user_id="user_alice",
            name="Alice: Team Tempo",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_alice_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_bob_1v1",
            user_id="user_bob",
            name="Bob: Mech Bastion",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_bob_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_bob_team",
            user_id="user_bob",
            name="Bob: Team Mechline",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_bob_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_carol_1v1",
            user_id="user_carol",
            name="Carol: Mist Sustain",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_carol_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_carol_team",
            user_id="user_carol",
            name="Carol: Team Sustain",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_carol_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_dave_1v1",
            user_id="user_dave",
            name="Dave: Void Spike",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_dave_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_dave_team",
            user_id="user_dave",
            name="Dave: Team Spike",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_dave_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_eve_1v1",
            user_id="user_eve",
            name="Eve: Vine Wall",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_eve_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_eve_team",
            user_id="user_eve",
            name="Eve: Team Beastpack",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_eve_team,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_frank_1v1",
            user_id="user_frank",
            name="Frank: Sun Vanguard",
            mode="1v1",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_frank_1v1,
        )
        _ensure_blueprint(
            session,
            blueprint_id="bp_lab_frank_team",
            user_id="user_frank",
            name="Frank: Team Knights",
            mode="team",
            status="submitted",
            ruleset_version=settings.ruleset_version,
            spec=lab_frank_team,
        )
        session.commit()

        if should_seed_matches:
            # Generate sample replays for the demo user's replay list + analytics.
            now = datetime.now(UTC)
            match_plans = [
                (
                    "m_seed_001",
                    "r_seed_001",
                    "1v1",
                    "bp_demo_1v1",
                    DEMO_USER_ID,
                    "bp_bot_ember_1v1",
                    "bot_ember",
                ),
                (
                    "m_seed_002",
                    "r_seed_002",
                    "1v1",
                    "bp_demo_1v1",
                    DEMO_USER_ID,
                    "bp_bot_mech_1v1",
                    "bot_mech",
                ),
                (
                    "m_seed_003",
                    "r_seed_003",
                    "1v1",
                    "bp_demo_1v1",
                    DEMO_USER_ID,
                    "bp_bot_crit_1v1",
                    "bot_crit",
                ),
                (
                    "m_seed_004",
                    "r_seed_004",
                    "1v1",
                    "bp_demo_storm_1v1",
                    DEMO_USER_ID,
                    "bp_bot_vine_1v1",
                    "bot_vine",
                ),
                (
                    "m_seed_005",
                    "r_seed_005",
                    "1v1",
                    "bp_demo_storm_1v1",
                    DEMO_USER_ID,
                    "bp_bot_slime_1v1",
                    "bot_slime",
                ),
                (
                    "m_seed_006",
                    "r_seed_006",
                    "1v1",
                    "bp_demo_void_1v1",
                    DEMO_USER_ID,
                    "bp_bot_mist_1v1",
                    "bot_mist",
                ),
                (
                    "m_seed_007",
                    "r_seed_007",
                    "1v1",
                    "bp_demo_vine_1v1",
                    DEMO_USER_ID,
                    "bp_bot_ember_1v1",
                    "bot_ember",
                ),
                (
                    "m_seed_008",
                    "r_seed_008",
                    "1v1",
                    "bp_demo_sun_1v1",
                    DEMO_USER_ID,
                    "bp_bot_mech_1v1",
                    "bot_mech",
                ),
                (
                    "m_seed_009",
                    "r_seed_009",
                    "1v1",
                    "bp_demo_sun_1v1",
                    DEMO_USER_ID,
                    "bp_bot_vine_1v1",
                    "bot_vine",
                ),
                (
                    "m_seed_010",
                    "r_seed_010",
                    "1v1",
                    "bp_demo_vine_1v1",
                    DEMO_USER_ID,
                    "bp_bot_crit_1v1",
                    "bot_crit",
                ),
                (
                    "m_seed_011",
                    "r_seed_011",
                    "team",
                    "bp_demo_team_mechline",
                    DEMO_USER_ID,
                    "bp_bot_mech_team",
                    "bot_mech",
                ),
                (
                    "m_seed_012",
                    "r_seed_012",
                    "team",
                    "bp_demo_team_mechline",
                    DEMO_USER_ID,
                    "bp_bot_burst_team",
                    "bot_ember",
                ),
                (
                    "m_seed_013",
                    "r_seed_013",
                    "team",
                    "bp_demo_team_mechline",
                    DEMO_USER_ID,
                    "bp_bot_slime_team",
                    "bot_slime",
                ),
                (
                    "m_seed_014",
                    "r_seed_014",
                    "team",
                    "bp_demo_team_mysticcircle",
                    DEMO_USER_ID,
                    "bp_bot_crit_team",
                    "bot_crit",
                ),
                (
                    "m_seed_015",
                    "r_seed_015",
                    "team",
                    "bp_demo_team_mysticcircle",
                    DEMO_USER_ID,
                    "bp_bot_mist_team",
                    "bot_mist",
                ),
                (
                    "m_seed_016",
                    "r_seed_016",
                    "team",
                    "bp_demo_team_mysticcircle",
                    DEMO_USER_ID,
                    "bp_bot_mech_team",
                    "bot_mech",
                ),
                (
                    "m_seed_017",
                    "r_seed_017",
                    "team",
                    "bp_demo_team_beastpack",
                    DEMO_USER_ID,
                    "bp_bot_vine_team",
                    "bot_vine",
                ),
                (
                    "m_seed_018",
                    "r_seed_018",
                    "team",
                    "bp_demo_team_beastpack",
                    DEMO_USER_ID,
                    "bp_bot_burst_team",
                    "bot_ember",
                ),
                (
                    "m_seed_019",
                    "r_seed_019",
                    "team",
                    "bp_demo_team_beastpack",
                    DEMO_USER_ID,
                    "bp_bot_slime_team",
                    "bot_slime",
                ),
                (
                    "m_seed_020",
                    "r_seed_020",
                    "team",
                    "bp_demo_team_mechline",
                    DEMO_USER_ID,
                    "bp_bot_crit_team",
                    "bot_crit",
                ),
            ]
            for idx, (
                match_id,
                replay_id,
                mode,
                bp_a_id,
                user_a_id,
                bp_b_id,
                user_b_id,
            ) in enumerate(match_plans, start=1):
                bp_a = session.get(Blueprint, bp_a_id)
                bp_b = session.get(Blueprint, bp_b_id)
                if not bp_a or not bp_b:
                    raise RuntimeError("Missing seeded blueprints")
                spec_a = BlueprintSpec.model_validate(orjson.loads(bp_a.spec_json))
                spec_b = BlueprintSpec.model_validate(orjson.loads(bp_b.spec_json))
                created_at = now - timedelta(hours=(len(match_plans) - idx))
                _ensure_match_and_replay(
                    session,
                    match_id=match_id,
                    replay_id=replay_id,
                    ruleset_version=settings.ruleset_version,
                    mode=mode,
                    seed_set_count=1,
                    user_a_id=user_a_id,
                    user_b_id=user_b_id,
                    blueprint_a_id=bp_a.id,
                    blueprint_b_id=bp_b.id,
                    spec_a=spec_a,
                    spec_b=spec_b,
                    created_at=created_at,
                )

            session.commit()

        demo_challenge_id = "ch_demo_clip_seed_001"
        try:
            if session.get(Challenge, demo_challenge_id) is None:
                from neuroleague_api.clip_render import best_clip_segment
                from neuroleague_api.storage import load_replay_json

                replay = session.get(Replay, "r_seed_001")
                match = session.get(Match, "m_seed_001")
                if replay and match:
                    payload = load_replay_json(artifact_path=replay.artifact_path)
                    st, et = best_clip_segment(payload, max_duration_sec=12.0)
                    session.add(
                        Challenge(
                            id=demo_challenge_id,
                            kind="clip",
                            target_blueprint_id=str(match.blueprint_a_id or "")
                            or None,
                            target_replay_id=str(replay.id),
                            start_sec=float(st) / 20.0,
                            end_sec=float(et) / 20.0,
                            mode=str(match.mode or "1v1"),
                            ruleset_version=str(
                                match.ruleset_version or settings.ruleset_version
                            ),
                            week_id=None,
                            portal_id=str(match.portal_id or "") or None,
                            augments_a_json=str(match.augments_a_json or "[]"),
                            augments_b_json=str(match.augments_b_json or "[]"),
                            creator_user_id=DEMO_USER_ID,
                            status="active",
                            created_at=datetime.now(UTC),
                        )
                    )
                    session.commit()
        except Exception:
            session.rollback()

        # Stable IDs for deploy smoke + share deep-links. Stored under /api/assets/ops/demo_ids.json.
        from neuroleague_api.storage import ensure_artifacts_dir
        from neuroleague_api.storage_backend import get_storage_backend

        ensure_artifacts_dir()
        demo_ids = {
            "generated_at": datetime.now(UTC).isoformat(),
            "ruleset_version": settings.ruleset_version,
            "clip_replay_id": "r_seed_001",
            "clip_match_id": "m_seed_001",
            "clip_challenge_id": demo_challenge_id,
            "best_build_id": "bp_demo_1v1",
            "best_team_build_id": "bp_demo_team_mechline",
            "featured_user_id": DEMO_USER_ID,
        }
        get_storage_backend().put_bytes(
            key="ops/demo_ids.json",
            data=orjson.dumps(
                demo_ids, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
            ),
            content_type="application/json",
        )

        # Launch-week engine defaults: quests + a small featured set (safe, idempotent).
        _ensure_cosmetic(
            session, cosmetic_id="badge_quest_daily_play_1", name="Daily Quest: Play 1"
        )
        _ensure_cosmetic(
            session,
            cosmetic_id="badge_quest_daily_watch_1",
            name="Daily Quest: Watch 1",
        )
        _ensure_cosmetic(
            session,
            cosmetic_id="badge_quest_daily_remix_or_beat_1",
            name="Daily Quest: Remix/Beat 1",
        )
        _ensure_cosmetic(
            session,
            cosmetic_id="badge_quest_weekly_ranked_5",
            name="Weekly Quest: Ranked 5",
        )
        _ensure_cosmetic(
            session,
            cosmetic_id="badge_quest_weekly_challenge_3",
            name="Weekly Quest: Challenges 3",
        )
        _ensure_cosmetic(
            session,
            cosmetic_id="badge_quest_weekly_share_3",
            name="Weekly Quest: Share 3",
        )

        _ensure_quest(
            session,
            cadence="daily",
            key="play_1",
            title="Play 1 match",
            description="Complete 1 match (ranked or challenge).",
            goal_count=1,
            event_type="match_done",
            reward_cosmetic_id="badge_quest_daily_play_1",
        )
        _ensure_quest(
            session,
            cadence="daily",
            key="watch_1",
            title="Watch 1 clip",
            description="Watch 1 clip to completion.",
            goal_count=1,
            event_type="clip_completion",
            reward_cosmetic_id="badge_quest_daily_watch_1",
        )
        _ensure_quest(
            session,
            cadence="daily",
            key="remix_or_beat_1",
            title="Remix or Beat This",
            description="Remix a build or accept a Beat This challenge.",
            goal_count=1,
            event_type="quest_remix_or_beat",
            reward_cosmetic_id="badge_quest_daily_remix_or_beat_1",
        )

        _ensure_quest(
            session,
            cadence="weekly",
            key="ranked_5",
            title="Ranked 5",
            description="Finish 5 ranked matches.",
            goal_count=5,
            event_type="ranked_done",
            reward_cosmetic_id="badge_quest_weekly_ranked_5",
        )
        _ensure_quest(
            session,
            cadence="weekly",
            key="challenge_3",
            title="Challenge 3",
            description="Accept 3 Beat This challenges.",
            goal_count=3,
            event_type="challenge_accept",
            reward_cosmetic_id="badge_quest_weekly_challenge_3",
        )
        _ensure_quest(
            session,
            cadence="weekly",
            key="share_3",
            title="Share 3",
            description="Share 3 times from the clips feed.",
            goal_count=3,
            event_type="share_action",
            reward_cosmetic_id="badge_quest_weekly_share_3",
        )

        _ensure_featured(
            session,
            kind="clip",
            target_id="r_seed_001",
            priority=100,
            title_override="Featured: Top Clip",
        )
        _ensure_featured(
            session,
            kind="build",
            target_id="bp_demo_1v1",
            priority=80,
            title_override="Featured: Build",
        )
        _ensure_featured(
            session,
            kind="user",
            target_id=DEMO_USER_ID,
            priority=50,
            title_override="Featured: Creator",
        )

        # Seed a small, deterministic-looking funnel so Ops dashboards are non-zero on day 0.
        now = datetime.now(UTC)
        yday = now - timedelta(days=1)
        device_id = "dev_seed_001"

        seeded_events: list[tuple[datetime, str | None, str, dict[str, Any]]] = [
            (
                yday,
                None,
                "share_open",
                {
                    "source": "s/clip",
                    "ref": None,
                    "device_id": device_id,
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                },
            ),
            (
                now,
                None,
                "share_open",
                {
                    "source": "s/clip",
                    "ref": None,
                    "device_id": device_id,
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "start_click",
                {
                    "source": "s/clip_open",
                    "ref": None,
                    "device_id": device_id,
                    "next": "/replay/m_seed_001",
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "guest_start_success",
                {
                    "method": "seed",
                    "ref": None,
                    "device_id": device_id,
                    "source": "s/clip_open",
                    "next": "/replay/m_seed_001",
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "first_replay_open",
                {
                    "match_id": "m_seed_001",
                    "replay_id": "r_seed_001",
                    "queue_type": "ranked",
                    "mode": "1v1",
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "ranked_queue",
                {
                    "match_id": "m_seed_001",
                    "mode": "1v1",
                    "blueprint_id": "bp_demo_1v1",
                    "opponent_type": "bot",
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "ranked_done",
                {
                    "match_id": "m_seed_001",
                    "mode": "1v1",
                    "result": "A",
                    "device_id": device_id,
                },
            ),
            # Demo mode funnel seed (Steam demo UX) — keep Ops non-zero on day 0.
            (
                now,
                None,
                "demo_run_start",
                {
                    "preset_id": "mech",
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "demo_run_done",
                {
                    "preset_id": "mech",
                    "match_id": "m_seed_001",
                    "replay_id": "r_seed_001",
                    "device_id": device_id,
                },
            ),
            (
                now,
                None,
                "demo_kit_download",
                {
                    "replay_id": "r_seed_001",
                    "device_id": device_id,
                },
            ),
            (
                now,
                None,
                "demo_beat_this_click",
                {
                    "challenge_id": "ch_demo_clip_seed_001",
                    "replay_id": "r_seed_001",
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "clip_view",
                {
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                    "source": "seed",
                    "meta": {},
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "clip_completion",
                {
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                    "source": "seed",
                    "meta": {"watched_pct": 0.9},
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "clip_share",
                {
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                    "source": "seed",
                    "meta": {"via": "copy_link"},
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "clip_fork_click",
                {
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                    "source": "seed",
                    "meta": {},
                    "device_id": device_id,
                },
            ),
            (
                now,
                DEMO_USER_ID,
                "clip_open_ranked",
                {
                    "replay_id": "r_seed_001",
                    "match_id": "m_seed_001",
                    "source": "seed",
                    "meta": {},
                    "device_id": device_id,
                },
            ),
        ]
        for created_at, user_id, typ, payload in seeded_events:
            session.add(
                Event(
                    id=f"ev_{uuid4().hex}",
                    user_id=user_id,
                    type=str(typ),
                    payload_json=orjson.dumps(payload).decode("utf-8"),
                    created_at=created_at,
                )
            )

        session.commit()

        try:
            from neuroleague_api.growth_metrics import rollup_growth_metrics

            rollup_growth_metrics(session, days=7)
        except Exception:
            session.commit()


if __name__ == "__main__":
    main()
