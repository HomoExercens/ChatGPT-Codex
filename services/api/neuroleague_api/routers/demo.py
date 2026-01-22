from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Literal

import orjson
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Blueprint, Challenge, Match, Replay, User
from neuroleague_api.storage import save_replay_json
from neuroleague_sim.canonical import canonical_json_bytes, canonical_sha256
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.simulate import simulate_match


router = APIRouter(prefix="/api/demo", tags=["demo"])

DEMO_PRESETS_VERSION: str = "demopresets_v1"
DEMO_RUN_VERSION: str = "demorun_v1"


@dataclass(frozen=True)
class DemoPreset:
    preset_id: str
    title: str
    subtitle: str
    player_blueprint_id: str
    bot_blueprint_id: str
    player_spec: BlueprintSpec
    bot_spec: BlueprintSpec


_PRESETS: dict[str, DemoPreset] = {
    "mech": DemoPreset(
        preset_id="mech",
        title="Mech Counter",
        subtitle="Clockwork burst with stable items",
        player_blueprint_id="bp_demo_1v1",
        bot_blueprint_id="bp_bot_ember_1v1",
        player_spec=BlueprintSpec(
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
        ),
        bot_spec=BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "ember_fox",
                    "formation": "front",
                    "items": {"weapon": "ember_blade", "armor": None, "utility": None},
                }
            ],
        ),
    ),
    "storm": DemoPreset(
        preset_id="storm",
        title="Storm Hawk",
        subtitle="Fast tempo + adrenaline spike",
        player_blueprint_id="bp_demo_storm_1v1",
        bot_blueprint_id="bp_bot_vine_1v1",
        player_spec=BlueprintSpec(
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
        ),
        bot_spec=BlueprintSpec(
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
        ),
    ),
    "void": DemoPreset(
        preset_id="void",
        title="Void Wisp",
        subtitle="Sharp opener + targeting array",
        player_blueprint_id="bp_demo_void_1v1",
        bot_blueprint_id="bp_bot_mist_1v1",
        player_spec=BlueprintSpec(
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
        ),
        bot_spec=BlueprintSpec(
            mode="1v1",
            team=[
                {
                    "creature_id": "mist_sage",
                    "formation": "front",
                    "items": {"weapon": None, "armor": "medic_vest", "utility": None},
                }
            ],
        ),
    ),
}


def _stable_hash_prefix(*, s: str, n: int = 12) -> str:
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()[: max(1, int(n))]


def _ensure_user(db: Session, *, user_id: str, display_name: str, is_guest: bool) -> None:
    if db.get(User, user_id) is not None:
        return
    now = datetime.now(UTC)
    db.add(
        User(
            id=user_id,
            username=None if is_guest else user_id,
            display_name=display_name,
            is_guest=bool(is_guest),
            created_at=now,
        )
    )
    db.commit()


def _ensure_blueprint(
    db: Session,
    *,
    blueprint_id: str,
    owner_user_id: str,
    name: str,
    spec: BlueprintSpec,
    ruleset_version: str,
) -> None:
    if db.get(Blueprint, blueprint_id) is not None:
        return
    now = datetime.now(UTC)
    spec_dict = spec.model_dump()
    db.add(
        Blueprint(
            id=blueprint_id,
            user_id=owner_user_id,
            name=name,
            mode=str(spec.mode),
            ruleset_version=str(ruleset_version),
            status="submitted",
            spec_json=canonical_json_bytes(spec_dict).decode("utf-8"),
            spec_hash=canonical_sha256(spec_dict),
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


class DemoPresetOut(BaseModel):
    id: str
    title: str
    subtitle: str
    blueprint_id: str


@router.get("/presets", response_model=list[DemoPresetOut])
def demo_presets() -> list[DemoPresetOut]:
    presets = []
    for p in _PRESETS.values():
        presets.append(
            DemoPresetOut(
                id=p.preset_id,
                title=p.title,
                subtitle=p.subtitle,
                blueprint_id=p.player_blueprint_id,
            )
        )
    presets.sort(key=lambda r: r.id)
    return presets


class DemoRunRequest(BaseModel):
    preset_id: Literal["mech", "storm", "void"] = Field(...)


class DemoRunResponse(BaseModel):
    match_id: str
    replay_id: str
    challenge_id: str
    blueprint_id: str
    share_url: str
    kit_url: str


@router.post("/run", response_model=DemoRunResponse)
def demo_run(
    req: DemoRunRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> DemoRunResponse:
    settings = Settings()
    preset = _PRESETS.get(str(req.preset_id))
    if not preset:
        raise HTTPException(status_code=400, detail="Unknown preset")

    # Unique per-user, deterministic (no randomness).
    user_hash = _stable_hash_prefix(s=f"{DEMO_RUN_VERSION}:{user_id}", n=12)
    match_id = f"m_demo_{preset.preset_id}_{user_hash}"
    replay_id = f"r_demo_{preset.preset_id}_{user_hash}"
    challenge_id = f"ch_demo_{preset.preset_id}_{user_hash}"

    # Ensure the preset blueprints exist even when seed-data isn't used.
    _ensure_user(db, user_id="user_demo", display_name="Dr. Kairos", is_guest=False)
    _ensure_user(db, user_id="bot_demo", display_name="Lab_Demo", is_guest=True)

    _ensure_blueprint(
        db,
        blueprint_id=preset.player_blueprint_id,
        owner_user_id="user_demo",
        name=f"Demo Preset: {preset.title}",
        spec=preset.player_spec,
        ruleset_version=settings.ruleset_version,
    )
    _ensure_blueprint(
        db,
        blueprint_id=preset.bot_blueprint_id,
        owner_user_id="bot_demo",
        name=f"Bot: {preset.title}",
        spec=preset.bot_spec,
        ruleset_version=settings.ruleset_version,
    )

    existing = db.get(Match, match_id)
    if existing:
        replay = db.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=409, detail="Replay not ready")
    else:
        now = datetime.now(UTC)
        replay_obj = simulate_match(
            match_id=match_id,
            seed_index=0,
            blueprint_a=preset.player_spec,
            blueprint_b=preset.bot_spec,
        )
        artifact_path = save_replay_json(
            replay_id=replay_id, payload=replay_obj.model_dump()
        )

        portal_id = str(replay_obj.header.portal_id or "") or None
        aug_a = [
            {"round": int(a.round), "augment_id": str(a.augment_id)}
            for a in (replay_obj.header.augments_a or [])
        ]
        aug_b = [
            {"round": int(a.round), "augment_id": str(a.augment_id)}
            for a in (replay_obj.header.augments_b or [])
        ]

        db.add(
            Match(
                id=match_id,
                queue_type="demo",
                week_id=None,
                mode=str(replay_obj.header.mode),
                ruleset_version=settings.ruleset_version,
                portal_id=portal_id,
                augments_a_json=orjson.dumps(aug_a).decode("utf-8"),
                augments_b_json=orjson.dumps(aug_b).decode("utf-8"),
                seed_set_count=1,
                user_a_id=user_id,
                user_b_id="bot_demo",
                blueprint_a_id=preset.player_blueprint_id,
                blueprint_b_id=preset.bot_blueprint_id,
                status="done",
                progress=100,
                ray_job_id=None,
                error_message=None,
                result=str(replay_obj.end_summary.winner),
                elo_delta_a=0,
                elo_delta_b=0,
                created_at=now,
                finished_at=now,
            )
        )
        db.add(
            Replay(
                id=replay_id,
                match_id=match_id,
                artifact_path=artifact_path,
                digest=str(replay_obj.digest),
                created_at=now,
            )
        )
        db.commit()

    # Ensure an active "Beat This" challenge exists for the demo clip.
    if db.get(Challenge, challenge_id) is None:
        from neuroleague_api.clip_render import best_clip_segment
        from neuroleague_api.storage import load_replay_json

        replay_row = db.get(Replay, replay_id)
        match_row = db.get(Match, match_id)
        if not replay_row or not match_row:
            raise HTTPException(status_code=500, detail="Demo replay missing")

        payload = load_replay_json(artifact_path=replay_row.artifact_path)
        st, et = best_clip_segment(payload, max_duration_sec=12.0)
        now = datetime.now(UTC)
        db.add(
            Challenge(
                id=challenge_id,
                kind="clip",
                target_blueprint_id=str(match_row.blueprint_a_id or "") or None,
                target_replay_id=replay_id,
                start_sec=float(st) / 20.0,
                end_sec=float(et) / 20.0,
                mode=str(match_row.mode or "1v1"),
                ruleset_version=str(match_row.ruleset_version or settings.ruleset_version),
                week_id=None,
                portal_id=str(match_row.portal_id or "") or None,
                augments_a_json=str(match_row.augments_a_json or "[]"),
                augments_b_json=str(match_row.augments_b_json or "[]"),
                creator_user_id=user_id,
                status="active",
                created_at=now,
            )
        )
        db.commit()

    # Share landing uses deterministic best-clip selection if start/end are omitted;
    # we include the range so the demo UX is stable and matches the challenge segment.
    from neuroleague_api.storage import load_replay_json
    from neuroleague_api.clip_render import best_clip_segment

    replay_row2 = db.get(Replay, replay_id)
    if not replay_row2:
        raise HTTPException(status_code=500, detail="Demo replay missing")
    payload2 = load_replay_json(artifact_path=replay_row2.artifact_path)
    st2, et2 = best_clip_segment(payload2, max_duration_sec=12.0)
    s = float(st2) / 20.0
    e = float(et2) / 20.0

    share_url = f"/s/clip/{replay_id}?start={s:.1f}&end={e:.1f}&v=1"
    kit_url = f"/s/clip/{replay_id}/kit.zip?start={s:.1f}&end={e:.1f}"

    return DemoRunResponse(
        match_id=match_id,
        replay_id=replay_id,
        challenge_id=challenge_id,
        blueprint_id=preset.player_blueprint_id,
        share_url=share_url,
        kit_url=kit_url,
    )

