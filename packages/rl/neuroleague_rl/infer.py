from __future__ import annotations

import os
from typing import Any, Literal

from neuroleague_rl.env import DraftBattleParallelEnv


def run_draft_policy_inference(
    *,
    checkpoint_path: str,
    mode: Literal["1v1", "team"],
    seed: int,
) -> dict[str, Any]:
    """
    Runs deterministic draft inference using an RLlib checkpoint and returns the
    env final infos payload (includes draft specs + draft logs).
    """
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

    from ray.rllib.algorithms.algorithm import Algorithm

    algo: Algorithm | None = None
    try:
        algo = Algorithm.from_checkpoint(checkpoint_path)
        env = DraftBattleParallelEnv(mode=mode)
        obs, _ = env.reset(seed=seed)

        while True:
            actions: dict[str, int] = {}
            for agent_id, agent_obs in obs.items():
                act = algo.compute_single_action(
                    agent_obs, policy_id="shared_policy", explore=False
                )
                if isinstance(act, tuple):
                    act = act[0]
                actions[agent_id] = int(act)

            obs, _, terms, truncs, infos = env.step(actions)
            if all(bool(v) for v in terms.values()) or all(
                bool(v) for v in truncs.values()
            ):
                # Env returns the same infos for all agents.
                return dict(infos.get("coach_a") or {})
    finally:
        if algo is not None:
            try:
                algo.stop()
            except Exception:  # noqa: BLE001
                pass
