from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from gymnasium import spaces
from pettingzoo.utils.env import ParallelEnv

from neuroleague_sim.catalog import (
    CREATURES,
    CREATURES_BY_RARITY,
    ITEMS,
    ITEMS_BY_RARITY_SLOT,
)
from neuroleague_sim.models import BlueprintSpec
from neuroleague_sim.modifiers import AUGMENTS, PORTALS, select_match_modifiers
from neuroleague_sim.simulate import simulate_match


AgentId = Literal["coach_a", "coach_b"]


@dataclass
class _CoachState:
    gold: int
    level: int
    team: list[str]
    weapon: str | None = None
    armor: str | None = None
    utility: str | None = None
    done_in_round: bool = False
    rerolls_this_round: int = 0


class DraftBattleParallelEnv(ParallelEnv):
    metadata = {"name": "neuroleague_draft_parallel_v15", "render_modes": []}

    def __init__(self, *, mode: Literal["1v1", "team"] = "1v1"):
        super().__init__()
        self.mode = mode
        self.team_size = 1 if mode == "1v1" else 3

        self.possible_agents = ["coach_a", "coach_b"]
        self.agents: list[AgentId] = []

        self._creature_ids = sorted(CREATURES.keys())
        self._item_ids = sorted(ITEMS.keys())
        self._creature_idx = {cid: i for i, cid in enumerate(self._creature_ids)}
        self._item_idx = {iid: i for i, iid in enumerate(self._item_ids)}
        self._rng: np.random.Generator | None = None

        self._round = 0  # 0..5
        self._actions_in_round = 0

        self._shop_creatures: dict[AgentId, list[str]] = {}
        self._shop_items: dict[AgentId, list[str]] = {}
        self._coach: dict[AgentId, _CoachState] = {}
        self._episode = 0
        self._draft_log: dict[AgentId, list[dict[str, Any]]] = {}
        self._match_id: str = "train_ep_0"
        self._match_modifiers: dict[str, Any] | None = None

        # Action space:
        # 0..2 buy creature slot i
        # 3..5 buy item slot i
        # 6 pass (end round for this coach)
        # 7 reroll (refresh current-round offers)
        # 8 level_up
        self._action_space = spaces.Discrete(9)

        # Observation:
        # round, gold, level,
        # shop creatures(3), shop items(3),
        # team creatures(team_size),
        # equipped ids(3),
        # rerolls_this_round
        obs_len = 3 + 3 + 3 + self.team_size + 3 + 1
        self._obs_space = spaces.Box(
            low=-1.0, high=999.0, shape=(obs_len,), dtype=np.float32
        )

    def _portal_rules(self) -> dict[str, Any]:
        if not self._match_modifiers:
            return {}
        pid = str(self._match_modifiers.get("portal_id") or "")
        pdef = PORTALS.get(pid)
        return dict(pdef.rules_json) if pdef else {}

    def _chosen_augment_ids(self, agent: AgentId) -> list[str]:
        if not self._match_modifiers:
            return []
        entries = (
            self._match_modifiers.get(
                "augments_a" if agent == "coach_a" else "augments_b"
            )
            or []
        )
        if not isinstance(entries, list):
            return []
        out: list[str] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            aid = str(e.get("augment_id") or "")
            if aid:
                out.append(aid)
        return out

    def _sum_draft_int(self, agent: AgentId, key: str) -> int:
        total = int(self._portal_rules().get(key) or 0)
        for aid in self._chosen_augment_ids(agent):
            adef = AUGMENTS.get(aid)
            if not adef:
                continue
            total += int(adef.rules_json.get(key) or 0)
        return int(total)

    def _draft_levelup_cost_min(self, agent: AgentId) -> int:
        m = int(self._portal_rules().get("draft_levelup_cost_min") or 1)
        for aid in self._chosen_augment_ids(agent):
            adef = AUGMENTS.get(aid)
            if not adef:
                continue
            m = max(m, int(adef.rules_json.get("draft_levelup_cost_min") or 1))
        return max(1, m)

    def _draft_rarity_bias(self, agent: AgentId) -> dict[str, float]:
        bias: dict[str, float] = {}
        pr = self._portal_rules().get("draft_rarity_bias")
        if isinstance(pr, dict):
            for k, v in pr.items():
                try:
                    bias[str(k)] = float(v)
                except Exception:  # noqa: BLE001
                    continue
        for aid in self._chosen_augment_ids(agent):
            adef = AUGMENTS.get(aid)
            if not adef:
                continue
            ar = adef.rules_json.get("draft_rarity_bias")
            if not isinstance(ar, dict):
                continue
            for k, v in ar.items():
                try:
                    bias[str(k)] = float(bias.get(str(k), 0.0)) + float(v)
                except Exception:  # noqa: BLE001
                    continue
        return bias

    def _draft_sigil_bias(self, agent: AgentId) -> int:
        return max(0, self._sum_draft_int(agent, "draft_sigil_bias"))

    def action_space(self, agent: str) -> spaces.Discrete:  # type: ignore[override]
        return self._action_space

    def observation_space(self, agent: str) -> spaces.Box:  # type: ignore[override]
        return self._obs_space

    def reset(self, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        self._episode += 1
        self.agents = list(self.possible_agents)
        self._rng = np.random.default_rng(seed)
        self._round = 0
        self._actions_in_round = 0
        seed_id = int(seed or 0)
        self._match_id = f"train_{self.mode}_{seed_id}_{self._episode}"
        try:
            self._match_modifiers = select_match_modifiers(self._match_id)
        except Exception:  # noqa: BLE001
            self._match_modifiers = None

        self._coach = {
            "coach_a": _CoachState(gold=10, level=1, team=[]),
            "coach_b": _CoachState(gold=10, level=1, team=[]),
        }

        self._draft_log = {"coach_a": [], "coach_b": []}
        self._start_round()

        obs = {a: self._obs(a) for a in self.agents}
        infos = {a: {} for a in self.agents}
        return obs, infos

    def step(self, actions: dict[str, int]):  # type: ignore[override]
        assert self._rng is not None
        a_action = int(actions.get("coach_a", 6))
        b_action = int(actions.get("coach_b", 6))

        self._apply_action("coach_a", a_action)
        self._apply_action("coach_b", b_action)

        self._actions_in_round += 1
        if self._should_advance_round():
            self._advance_round()

        draft_rounds = int(self._portal_rules().get("draft_rounds") or 6)
        draft_rounds = max(1, min(12, draft_rounds))
        terminated = self._round >= draft_rounds

        if not terminated:
            obs = {a: self._obs(a) for a in self.agents}
            rewards = {a: 0.0 for a in self.agents}
            terminations = {a: False for a in self.agents}
            truncations = {a: False for a in self.agents}
            infos = {a: {} for a in self.agents}
            return obs, rewards, terminations, truncations, infos

        # Episode end: simulate battle between the two drafted builds.
        spec_a = self._to_blueprint(self._coach["coach_a"])
        spec_b = self._to_blueprint(self._coach["coach_b"])
        replay = simulate_match(
            match_id=self._match_id,
            seed_index=0,
            blueprint_a=spec_a,
            blueprint_b=spec_b,
            modifiers=self._match_modifiers,
        )

        winner = replay.end_summary.winner
        if winner == "A":
            rewards = {"coach_a": 1.0, "coach_b": 0.0}
        elif winner == "B":
            rewards = {"coach_a": 0.0, "coach_b": 1.0}
        else:
            rewards = {"coach_a": 0.5, "coach_b": 0.5}

        obs = {a: self._obs(a) for a in self.agents}
        terminations = {a: True for a in self.agents}
        truncations = {a: False for a in self.agents}
        infos: dict[str, Any] = {
            "winner": winner,
            "digest": replay.digest,
            "match_id": self._match_id,
            "modifiers": self._match_modifiers or {},
            "draft_spec_a": spec_a.model_dump(),
            "draft_spec_b": spec_b.model_dump(),
            "draft_log_a": self._draft_log.get("coach_a", []),
            "draft_log_b": self._draft_log.get("coach_b", []),
        }
        return obs, rewards, terminations, truncations, {a: infos for a in self.agents}

    def _apply_action(self, agent: AgentId, action: int) -> None:
        state = self._coach[agent]

        if state.done_in_round:
            action = 6

        if action == 6:
            if not state.done_in_round:
                state.done_in_round = True
                self._log_action(agent, {"type": "pass"})
            return

        if action == 7:
            base_cost = max(
                0, 1 + self._sum_draft_int(agent, "draft_reroll_cost_delta")
            )
            free = max(0, self._sum_draft_int(agent, "draft_free_reroll_per_round"))
            cost = 0 if state.rerolls_this_round < free else base_cost
            ok = state.gold >= cost
            if ok:
                state.gold -= cost
                state.rerolls_this_round += 1
                self._roll_shop_for(agent)
            self._log_action(
                agent,
                {
                    "type": "reroll",
                    "ok": ok,
                    "cost": int(cost),
                    "free_used": bool(cost == 0),
                    "shop": {
                        "creatures": list(self._shop_creatures[agent]),
                        "items": list(self._shop_items[agent]),
                    },
                },
            )
            return

        if action == 8:
            level_up_cost = {1: 4, 2: 6, 3: 8, 4: 10}
            if state.level >= 5:
                self._log_action(agent, {"type": "level_up", "ok": False})
                return
            base = int(level_up_cost[state.level])
            delta = self._sum_draft_int(agent, "draft_levelup_cost_delta")
            cost = max(self._draft_levelup_cost_min(agent), base + delta)
            ok = state.gold >= cost
            if ok:
                before = state.level
                state.gold -= cost
                state.level += 1
                self._log_action(
                    agent,
                    {
                        "type": "level_up",
                        "ok": True,
                        "from": before,
                        "to": state.level,
                        "cost": cost,
                    },
                )
            else:
                self._log_action(agent, {"type": "level_up", "ok": False, "cost": cost})
            return

        if action in (0, 1, 2):
            creature_id = self._shop_creatures[agent][action]
            rarity = int(CREATURES[creature_id].rarity)
            creature_cost = {1: 4, 2: 6, 3: 8}[rarity]
            ok = state.gold >= creature_cost and len(state.team) < self.team_size
            if ok:
                state.team.append(creature_id)
                state.gold -= creature_cost
            self._log_action(
                agent,
                {
                    "type": "buy_creature",
                    "ok": ok,
                    "slot": int(action),
                    "creature_id": creature_id,
                    "rarity": rarity,
                    "cost": creature_cost,
                },
            )
            return

        if action in (3, 4, 5):
            item_id = self._shop_items[agent][action - 3]
            rarity = int(ITEMS[item_id].rarity)
            item_cost = {1: 2, 2: 4, 3: 6}[rarity]
            ok = state.gold >= item_cost and bool(state.team)
            slot = ITEMS[item_id].slot
            replaced: str | None = None
            if ok:
                state.gold -= item_cost
                replaced = getattr(state, slot)
                setattr(state, slot, item_id)
            self._log_action(
                agent,
                {
                    "type": "buy_item",
                    "ok": ok,
                    "slot": int(action - 3),
                    "item_id": item_id,
                    "item_slot": slot,
                    "rarity": rarity,
                    "cost": item_cost,
                    "replaced": replaced,
                },
            )
            return

        self._log_action(agent, {"type": "unknown", "action": int(action)})

    def _to_blueprint(self, coach: _CoachState) -> BlueprintSpec:
        team_ids = list(coach.team)
        while len(team_ids) < self.team_size:
            team_ids.append("slime_knight")

        slots: list[dict[str, Any]] = []
        for i, cid in enumerate(team_ids[: self.team_size]):
            slots.append(
                {
                    "creature_id": cid,
                    "formation": "front" if i < 2 else "back",
                    "items": {
                        "weapon": coach.weapon,
                        "armor": coach.armor,
                        "utility": coach.utility,
                    },
                }
            )
        return BlueprintSpec(mode=self.mode, team=slots)

    def _rarity_probs(self, level: int) -> list[tuple[int, float]]:
        table: dict[int, list[tuple[int, float]]] = {
            1: [(1, 1.0)],
            2: [(1, 0.8), (2, 0.2)],
            3: [(1, 0.6), (2, 0.3), (3, 0.1)],
            4: [(1, 0.4), (2, 0.4), (3, 0.2)],
            5: [(1, 0.2), (2, 0.5), (3, 0.3)],
        }
        return table.get(int(level), table[1])

    def _sample_rarity(self, level: int, agent: AgentId) -> int:
        assert self._rng is not None
        probs = self._rarity_probs(level)
        bias = self._draft_rarity_bias(agent)
        r3_bonus = float(bias.get("r3_bonus", 0.0))
        if r3_bonus and any(r == 3 for (r, _p) in probs):
            probs_map = {int(r): float(p) for (r, p) in probs}
            take = min(max(0.0, r3_bonus), float(probs_map.get(1, 0.0)))
            probs_map[1] = float(probs_map.get(1, 0.0)) - take
            probs_map[3] = float(probs_map.get(3, 0.0)) + take
            total = sum(float(p) for p in probs_map.values())
            if total > 0:
                probs = sorted(
                    [(int(r), float(p) / total) for r, p in probs_map.items()],
                    key=lambda t: t[0],
                )

        roll = float(self._rng.random())
        acc = 0.0
        last = 1
        for rarity, p in probs:
            last = rarity
            acc += float(p)
            if roll <= acc:
                return int(rarity)
        return int(last)

    def _roll_shop_for(self, agent: AgentId) -> None:
        state = self._coach[agent]
        assert self._rng is not None

        extra_creature_rolls = max(
            0, self._sum_draft_int(agent, "draft_shop_creature_slots_delta")
        )
        creature_rolls = 3 + int(extra_creature_rolls)
        creature_candidates: list[str] = []
        for _ in range(max(3, creature_rolls)):
            rarity = self._sample_rarity(state.level, agent)
            pool = CREATURES_BY_RARITY.get(rarity) or CREATURES_BY_RARITY[1]
            creature_candidates.append(pool[int(self._rng.integers(0, len(pool)))])

        if creature_rolls > 3:
            creature_candidates.sort(
                key=lambda cid: (-int(CREATURES[cid].rarity), str(cid))
            )
        creatures = creature_candidates[:3]

        extra_item_rolls = max(
            0, self._sum_draft_int(agent, "draft_shop_item_slots_delta")
        )
        item_rolls = 3 + int(extra_item_rolls)
        sigil_bias = self._draft_sigil_bias(agent)
        sigil_weight = int(sigil_bias) if sigil_bias else 0

        items: list[str] = []
        for slot in ("weapon", "armor", "utility"):
            item_candidates: list[str] = []
            for _ in range(max(3, item_rolls)):
                rarity = self._sample_rarity(state.level, agent)
                pool = (
                    ITEMS_BY_RARITY_SLOT.get(slot, {}).get(rarity)
                    or ITEMS_BY_RARITY_SLOT.get(slot, {}).get(1)
                    or []
                )
                if not pool:
                    pool = self._item_ids
                item_candidates.append(pool[int(self._rng.integers(0, len(pool)))])

            if item_rolls > 3 or sigil_bias:
                item_candidates.sort(
                    key=lambda iid: (
                        -int(bool(getattr(ITEMS.get(iid), "synergy_bonus", None)))
                        * sigil_weight,
                        -int(getattr(ITEMS.get(iid), "rarity", 1) or 1),
                        str(iid),
                    )
                )
            items.append(item_candidates[0])

        self._shop_creatures[agent] = creatures
        self._shop_items[agent] = items

    def _start_round(self) -> None:
        self._actions_in_round = 0
        for agent in self.possible_agents:
            st = self._coach[agent]  # type: ignore[index]
            st.done_in_round = False
            st.rerolls_this_round = 0
            self._roll_shop_for(agent)  # initial offers per round

            self._draft_log[agent].append(
                {
                    "round": int(self._round + 1),
                    "start_gold": int(st.gold),
                    "start_level": int(st.level),
                    "start_shop": {
                        "creatures": list(self._shop_creatures[agent]),
                        "items": list(self._shop_items[agent]),
                    },
                    "actions": [],
                }
            )

    def _finalize_round_log(self, agent: AgentId) -> None:
        st = self._coach[agent]
        if not self._draft_log.get(agent):
            return
        log = self._draft_log[agent][-1]
        log["end_gold"] = int(st.gold)
        log["end_level"] = int(st.level)
        log["end_team"] = list(st.team)
        log["end_equip"] = {
            "weapon": st.weapon,
            "armor": st.armor,
            "utility": st.utility,
        }
        log["end_shop"] = {
            "creatures": list(self._shop_creatures.get(agent, [])),
            "items": list(self._shop_items.get(agent, [])),
        }

    def _log_action(self, agent: AgentId, payload: dict[str, Any]) -> None:
        if not self._draft_log.get(agent):
            return
        actions = self._draft_log[agent][-1].setdefault("actions", [])
        if isinstance(actions, list):
            actions.append(payload)

    def _should_advance_round(self) -> bool:
        if all(self._coach[a].done_in_round for a in self.possible_agents):  # type: ignore[index]
            return True
        return self._actions_in_round >= 10

    def _advance_round(self) -> None:
        for agent in self.possible_agents:
            self._finalize_round_log(agent)  # type: ignore[arg-type]

        self._round += 1
        draft_rounds = int(self._portal_rules().get("draft_rounds") or 6)
        draft_rounds = max(1, min(12, draft_rounds))
        if self._round >= draft_rounds:
            return

        # Round start income.
        for agent in self.possible_agents:
            inc = 5 + self._sum_draft_int(agent, "draft_income_delta")  # type: ignore[arg-type]
            self._coach[agent].gold += int(inc)  # type: ignore[index]

        self._start_round()

    def _obs(self, agent: AgentId) -> np.ndarray:
        state = self._coach[agent]
        r = min(self._round, 5)
        creatures = self._shop_creatures.get(agent, [])
        items = self._shop_items.get(agent, [])

        def cidx(cid: str | None) -> int:
            if not cid:
                return -1
            return self._creature_idx.get(cid, -1)

        def iidx(iid: str | None) -> int:
            if not iid:
                return -1
            return self._item_idx.get(iid, -1)

        team_vec = [
            cidx(cid)
            for cid in (state.team + [None] * self.team_size)[: self.team_size]
        ]
        equip_vec = [iidx(state.weapon), iidx(state.armor), iidx(state.utility)]
        vec = [
            float(r),
            float(state.gold),
            float(state.level),
            float(cidx(creatures[0] if len(creatures) > 0 else None)),
            float(cidx(creatures[1] if len(creatures) > 1 else None)),
            float(cidx(creatures[2] if len(creatures) > 2 else None)),
            float(iidx(items[0] if len(items) > 0 else None)),
            float(iidx(items[1] if len(items) > 1 else None)),
            float(iidx(items[2] if len(items) > 2 else None)),
            *[float(x) for x in team_vec],
            *[float(x) for x in equip_vec],
            float(state.rerolls_this_round),
        ]
        return np.asarray(vec, dtype=np.float32)
