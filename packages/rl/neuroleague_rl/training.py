from __future__ import annotations

from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.env.wrappers.pettingzoo_env import ParallelPettingZooEnv
from ray.rllib.policy.policy import PolicySpec
from ray.tune.registry import register_env

from neuroleague_rl.env import DraftBattleParallelEnv


def _env_creator(config: dict):
    mode = config.get("mode", "1v1")
    return ParallelPettingZooEnv(DraftBattleParallelEnv(mode=mode))


def build_ppo_config(*, mode: str = "1v1") -> PPOConfig:
    register_env("neuroleague_draft_parallel_v15", _env_creator)

    cfg = (
        PPOConfig()
        .environment(env="neuroleague_draft_parallel_v15", env_config={"mode": mode})
        .framework(framework="torch")
        .env_runners(
            num_env_runners=0, create_local_env_runner=True, rollout_fragment_length=50
        )
        .training(train_batch_size=400, minibatch_size=64, num_epochs=1, lr=5e-4)
        .resources(num_gpus=0)
        .multi_agent(
            policies={"shared_policy": PolicySpec()},
            policy_mapping_fn=lambda agent_id, *args, **kwargs: "shared_policy",
        )
    )
    return cfg
