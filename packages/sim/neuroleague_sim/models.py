from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from neuroleague_sim.catalog import CREATURES, ITEMS, Formation, TeamMode


class ItemsSpec(BaseModel):
    weapon: str | None = None
    armor: str | None = None
    utility: str | None = None

    @model_validator(mode="after")
    def _validate_ids(self) -> "ItemsSpec":
        for slot in ("weapon", "armor", "utility"):
            item_id = getattr(self, slot)
            if item_id is None:
                continue
            item = ITEMS.get(item_id)
            if not item:
                raise ValueError(f"unknown item_id: {item_id}")
            if item.slot != slot:
                raise ValueError(f"item {item_id} is slot={item.slot}, not {slot}")
        return self


class CreatureSlotSpec(BaseModel):
    creature_id: str
    formation: Formation = "front"
    items: ItemsSpec = Field(default_factory=ItemsSpec)

    @model_validator(mode="after")
    def _validate_creature(self) -> "CreatureSlotSpec":
        if self.creature_id not in CREATURES:
            raise ValueError(f"unknown creature_id: {self.creature_id}")
        return self


class BlueprintSpec(BaseModel):
    ruleset_version: str = "2026S1-v1"
    mode: TeamMode
    team: list[CreatureSlotSpec]

    @model_validator(mode="after")
    def _validate_team_size(self) -> "BlueprintSpec":
        if self.mode == "1v1" and len(self.team) != 1:
            raise ValueError("mode=1v1 requires exactly 1 creature")
        if self.mode == "team" and len(self.team) != 3:
            raise ValueError("mode=team requires exactly 3 creatures")
        return self


ReplayEventType = Literal[
    "PORTAL_SELECTED",
    "AUGMENT_OFFERED",
    "AUGMENT_CHOSEN",
    "AUGMENT_TRIGGER",
    "SYNERGY_TRIGGER",
    "ATTACK",
    "DAMAGE",
    "HEAL",
    "DEATH",
    "END",
]


class ReplayEvent(BaseModel):
    t: int = Field(ge=0)
    type: ReplayEventType
    payload: dict[str, Any] = Field(default_factory=dict)


class ReplayHighlight(BaseModel):
    rank: int = Field(ge=1)
    start_t: int = Field(ge=0)
    end_t: int = Field(ge=0)
    title: str
    summary: str
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_range(self) -> "ReplayHighlight":
        if self.end_t < self.start_t:
            raise ValueError("end_t must be >= start_t")
        return self


class ReplayHeader(BaseModel):
    ruleset_version: str
    pack_hash: str | None = None
    match_id: str
    seed_index: int
    seed: int
    mode: TeamMode
    blueprint_a_hash: str
    blueprint_b_hash: str
    portal_id: str | None = None
    augments_a: list["ReplayAugmentChoice"] = Field(default_factory=list)
    augments_b: list["ReplayAugmentChoice"] = Field(default_factory=list)
    units: list["ReplayUnit"] = Field(default_factory=list)


class ReplayAugmentChoice(BaseModel):
    round: int = Field(ge=0)
    augment_id: str


class ReplayUnit(BaseModel):
    unit_id: str
    team: Literal["A", "B"]
    slot_index: int = Field(ge=0)
    formation: Formation
    creature_id: str
    creature_name: str
    role: str
    tags: list[str] = Field(default_factory=list)
    items: ItemsSpec = Field(default_factory=ItemsSpec)
    max_hp: int = Field(ge=1)


class ReplayEndSummary(BaseModel):
    winner: Literal["A", "B", "draw"]
    duration_ticks: int = Field(ge=0)
    hp_a: int = Field(ge=0)
    hp_b: int = Field(ge=0)


class Replay(BaseModel):
    header: ReplayHeader
    timeline_events: list[ReplayEvent]
    end_summary: ReplayEndSummary
    highlights: list[ReplayHighlight] = Field(default_factory=list)
    digest: str
