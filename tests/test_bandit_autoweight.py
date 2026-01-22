from __future__ import annotations

import orjson


def _weights(exp) -> dict[str, float]:
    raw = orjson.loads(exp.variants_json or "[]")
    out: dict[str, float] = {}
    for v in raw:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("id") or "")
        if not vid:
            continue
        out[vid] = float(v.get("weight") or 0.0)
    return out


def test_bandit_promotes_winner_with_guardrails() -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.experiments import (
        BANDIT_VERSION,
        bandit_update_for_experiment,
        ensure_default_experiments,
    )
    from neuroleague_api.models import Experiment

    with SessionLocal() as session:
        ensure_default_experiments(session)
        exp = session.get(Experiment, "clip_len_v1")
        assert exp is not None
        exp.variants_json = orjson.dumps(
            [
                {"id": "10s", "weight": 0.34, "config": {}},
                {"id": "12s", "weight": 0.33, "config": {}},
                {"id": "15s", "weight": 0.33, "config": {}},
            ]
        ).decode("utf-8")
        exp.config_json = orjson.dumps(
            {
                BANDIT_VERSION: {
                    "enabled": True,
                    "baseline": "12s",
                    "threshold_n": 10,
                    "margin": 0.01,
                    "min_share": 0.10,
                    "max_share": 0.80,
                    "step": 0.20,
                }
            }
        ).decode("utf-8")
        session.add(exp)
        session.commit()

        before = _weights(exp)
        table = {
            "key": "clip_len_v1",
            "variants": [
                {"id": "10s", "n": 120, "ranked_done_rate": 0.18},
                {"id": "12s", "n": 120, "ranked_done_rate": 0.10},
                {"id": "15s", "n": 120, "ranked_done_rate": 0.09},
            ],
        }
        res = bandit_update_for_experiment(
            session, experiment_key="clip_len_v1", table=table
        )
        assert res.get("ok") is True
        assert res.get("winner") == "10s"
        assert res.get("changed") is True

        session.refresh(exp)
        after = _weights(exp)
        assert after["10s"] > before["10s"]
        assert after["10s"] <= 0.80 + 1e-6
        assert after["12s"] >= 0.10 - 1e-6
        assert abs(sum(after.values()) - 1.0) < 1e-6


def test_bandit_override_weights_take_precedence() -> None:
    from neuroleague_api.db import SessionLocal
    from neuroleague_api.experiments import (
        BANDIT_VERSION,
        bandit_update_for_experiment,
        ensure_default_experiments,
    )
    from neuroleague_api.models import Experiment

    with SessionLocal() as session:
        ensure_default_experiments(session)
        exp = session.get(Experiment, "captions_v2")
        assert exp is not None
        exp.config_json = orjson.dumps(
            {
                BANDIT_VERSION: {
                    "enabled": True,
                    "override_weights": {"A": 0.1, "B": 0.8, "C": 0.1},
                    "min_share": 0.10,
                    "max_share": 0.80,
                }
            }
        ).decode("utf-8")
        session.add(exp)
        session.commit()

        res = bandit_update_for_experiment(
            session,
            experiment_key="captions_v2",
            table={
                "key": "captions_v2",
                "variants": [
                    {"id": "A", "n": 999, "ranked_done_rate": 0.9},
                    {"id": "B", "n": 999, "ranked_done_rate": 0.1},
                    {"id": "C", "n": 999, "ranked_done_rate": 0.1},
                ],
            },
        )
        assert res.get("ok") is True
        assert res.get("mode") == "override"

        session.refresh(exp)
        after = _weights(exp)
        assert after["B"] >= after["A"]
        assert after["B"] >= after["C"]
