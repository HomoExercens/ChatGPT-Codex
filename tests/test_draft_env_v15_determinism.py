from __future__ import annotations

import pytest

from neuroleague_rl.env import DraftBattleParallelEnv
from neuroleague_sim.canonical import canonical_sha256


@pytest.mark.parametrize("mode", ["1v1", "team"])
def test_draft_env_v15_determinism_same_seed_same_actions(mode: str) -> None:
    def run_once(seed: int) -> dict:
        env = DraftBattleParallelEnv(mode=mode)  # type: ignore[arg-type]
        env.reset(seed=seed)

        # Fixed action script: buy, buy, reroll, level, pass (repeat per round).
        script = []
        for _ in range(6):
            script.extend(
                [
                    {"coach_a": 0, "coach_b": 0},
                    {"coach_a": 3, "coach_b": 3},
                    {"coach_a": 7, "coach_b": 7},
                    {"coach_a": 8, "coach_b": 8},
                    {"coach_a": 6, "coach_b": 6},
                ]
            )

        infos_final: dict | None = None
        for actions in script:
            _, _, terms, _, infos = env.step(actions)
            if all(bool(v) for v in terms.values()):
                infos_final = infos["coach_a"]
                break

        assert infos_final is not None
        return infos_final

    a = run_once(seed=123)
    b = run_once(seed=123)

    assert a.get("draft_spec_a") == b.get("draft_spec_a")
    assert canonical_sha256(a.get("draft_log_a")) == canonical_sha256(
        b.get("draft_log_a")
    )
