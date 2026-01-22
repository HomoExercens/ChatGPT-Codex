from __future__ import annotations

from datetime import UTC, datetime

import orjson


def _login_demo(api_client) -> dict[str, str]:
    login = api_client.post("/api/auth/login", json={"username": "demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_to_blueprint_fallback_when_checkpoint_missing(api_client) -> None:
    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Blueprint, Checkpoint, TrainingRun

    headers = _login_demo(api_client)
    now = datetime.now(UTC)
    settings = Settings()

    run_id = "tr_test_missing_ckpt"
    ckpt_id = "ckpt_tr_test_missing_ckpt_0001"

    with SessionLocal() as session:
        session.add(
            TrainingRun(
                id=run_id,
                user_id="user_demo",
                ruleset_version=settings.ruleset_version,
                mode="1v1",
                plan="Stable",
                budget_tokens=100,
                status="done",
                progress=100,
                metrics_json="{}",
                created_at=now,
                updated_at=now,
                started_at=now,
                ended_at=now,
                ray_job_id=None,
            )
        )
        session.add(
            Checkpoint(
                id=ckpt_id,
                training_run_id=run_id,
                step=1,
                metrics_json="{}",
                artifact_path=None,
                created_at=now,
            )
        )
        session.commit()

    resp = api_client.post(
        f"/api/training/runs/{run_id}/to-blueprint",
        json={"checkpoint_id": ckpt_id, "name": "Fallback BP"},
        headers=headers,
    )
    assert resp.status_code == 200
    blueprint_id = resp.json()["blueprint_id"]

    with SessionLocal() as session:
        bp = session.get(Blueprint, blueprint_id)
        assert bp is not None
        meta = orjson.loads(bp.meta_json)
        assert meta.get("note") == "fallback_deterministic"


def test_to_blueprint_policy_inference_stores_meta(api_client, monkeypatch) -> None:
    from neuroleague_api.core.config import Settings
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.models import Blueprint, Checkpoint, TrainingRun

    headers = _login_demo(api_client)
    now = datetime.now(UTC)
    settings = Settings()

    run_id = "tr_test_policy_ckpt"
    ckpt_id = "ckpt_tr_test_policy_ckpt_0001"

    with SessionLocal() as session:
        session.add(
            TrainingRun(
                id=run_id,
                user_id="user_demo",
                ruleset_version=settings.ruleset_version,
                mode="1v1",
                plan="Stable",
                budget_tokens=100,
                status="done",
                progress=100,
                metrics_json="{}",
                created_at=now,
                updated_at=now,
                started_at=now,
                ended_at=now,
                ray_job_id=None,
            )
        )
        session.add(
            Checkpoint(
                id=ckpt_id,
                training_run_id=run_id,
                step=1,
                metrics_json="{}",
                artifact_path="/tmp/fake_checkpoint",
                created_at=now,
            )
        )
        session.commit()

    import neuroleague_api.routers.training as training_router
    import neuroleague_rl.infer as infer

    monkeypatch.setattr(training_router, "ensure_ray", lambda: None)

    def fake_infer(*, checkpoint_path: str, mode: str, seed: int):  # noqa: ARG001
        return {
            "draft_spec_a": {
                "ruleset_version": settings.ruleset_version,
                "mode": "1v1",
                "team": [
                    {
                        "creature_id": "slime_knight",
                        "formation": "front",
                        "items": {"weapon": None, "armor": None, "utility": None},
                    }
                ],
            },
            "draft_log_a": [
                {
                    "round": 1,
                    "start_gold": 10,
                    "start_level": 1,
                    "start_shop": {
                        "creatures": ["slime_knight"],
                        "items": ["targeting_array"],
                    },
                    "actions": [{"type": "pass"}],
                    "end_gold": 10,
                    "end_level": 1,
                }
            ],
        }

    monkeypatch.setattr(infer, "run_draft_policy_inference", fake_infer)

    resp = api_client.post(
        f"/api/training/runs/{run_id}/to-blueprint",
        json={"checkpoint_id": ckpt_id, "name": "Policy BP"},
        headers=headers,
    )
    assert resp.status_code == 200
    blueprint_id = resp.json()["blueprint_id"]

    with SessionLocal() as session:
        bp = session.get(Blueprint, blueprint_id)
        assert bp is not None
        meta = orjson.loads(bp.meta_json)
        assert meta.get("note") == "policy_inference"
        assert "draft_log" in meta
