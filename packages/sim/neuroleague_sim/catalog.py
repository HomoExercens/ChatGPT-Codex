from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


TeamMode = Literal["1v1", "team"]
Formation = Literal["front", "back"]
RangeType = Literal["melee", "ranged"]


@dataclass(frozen=True)
class CreatureDef:
    id: str
    name: str
    role: Literal["Tank", "DPS", "Support"]
    range: RangeType
    tags: tuple[str, str]
    max_hp: int
    atk: int
    attack_interval_ticks: int  # at 20 ticks/sec
    heal_interval_ticks: int | None = None
    rarity: int = 1  # 1..3


@dataclass(frozen=True)
class ItemDef:
    id: str
    slot: Literal["weapon", "armor", "utility"]
    name: str
    rarity: int = 1  # 1..3
    atk_permille: int = 0
    hp_permille: int = 0
    crit_permille: int = 0
    damage_reduction_permille: int = 0
    speed_permille: int = 0
    synergy_bonus: dict[str, int] = field(default_factory=dict)
    badge_text: str | None = None


CREATURES: dict[str, CreatureDef] = {
    "slime_knight": CreatureDef(
        id="slime_knight",
        name="Slime Knight",
        role="Tank",
        range="melee",
        tags=("Gelatinous", "Knight"),
        max_hp=1200,
        atk=50,
        attack_interval_ticks=25,
    ),
    "ember_fox": CreatureDef(
        id="ember_fox",
        name="Ember Fox",
        role="DPS",
        range="ranged",
        tags=("Beast", "Fire"),
        max_hp=600,
        atk=180,
        attack_interval_ticks=14,
    ),
    "clockwork_golem": CreatureDef(
        id="clockwork_golem",
        name="Clockwork Golem",
        role="Tank",
        range="melee",
        tags=("Mech", "Heavy"),
        max_hp=2000,
        atk=80,
        attack_interval_ticks=40,
        rarity=2,
    ),
    "crystal_weaver": CreatureDef(
        id="crystal_weaver",
        name="Crystal Weaver",
        role="Support",
        range="ranged",
        tags=("Crystal", "Mystic"),
        max_hp=900,
        atk=110,
        attack_interval_ticks=20,
        heal_interval_ticks=40,
    ),
    "field_medic": CreatureDef(
        id="field_medic",
        name="Field Medic",
        role="Support",
        range="ranged",
        tags=("Medic", "Mystic"),
        max_hp=850,
        atk=90,
        attack_interval_ticks=22,
        heal_interval_ticks=35,
    ),
    "iron_striker": CreatureDef(
        id="iron_striker",
        name="Iron Striker",
        role="DPS",
        range="melee",
        tags=("Mech", "Knight"),
        max_hp=900,
        atk=140,
        attack_interval_ticks=18,
    ),
    "thornback_boar": CreatureDef(
        id="thornback_boar",
        name="Thornback Boar",
        role="Tank",
        range="melee",
        tags=("Vine", "Beast"),
        max_hp=1500,
        atk=75,
        attack_interval_ticks=26,
    ),
    "mist_sage": CreatureDef(
        id="mist_sage",
        name="Mist Sage",
        role="Support",
        range="ranged",
        tags=("Mist", "Mystic"),
        max_hp=950,
        atk=105,
        attack_interval_ticks=22,
        heal_interval_ticks=30,
    ),
    "storm_hawk": CreatureDef(
        id="storm_hawk",
        name="Storm Hawk",
        role="DPS",
        range="ranged",
        tags=("Storm", "Beast"),
        max_hp=650,
        atk=165,
        attack_interval_ticks=15,
    ),
    "sun_paladin": CreatureDef(
        id="sun_paladin",
        name="Sun Paladin",
        role="Tank",
        range="melee",
        tags=("Knight", "Fire"),
        max_hp=1700,
        atk=95,
        attack_interval_ticks=28,
        rarity=2,
    ),
    "void_wisp": CreatureDef(
        id="void_wisp",
        name="Void Wisp",
        role="DPS",
        range="ranged",
        tags=("Void", "Mystic"),
        max_hp=520,
        atk=210,
        attack_interval_ticks=19,
        rarity=3,
    ),
    "scrap_artificer": CreatureDef(
        id="scrap_artificer",
        name="Scrap Artificer",
        role="Support",
        range="ranged",
        tags=("Scrap", "Mech"),
        max_hp=820,
        atk=95,
        attack_interval_ticks=20,
        heal_interval_ticks=36,
    ),
}


ITEMS: dict[str, ItemDef] = {
    "plasma_lance": ItemDef(
        id="plasma_lance",
        slot="weapon",
        name="Plasma Lance",
        rarity=2,
        atk_permille=150,
        crit_permille=50,
    ),
    "ember_blade": ItemDef(
        id="ember_blade",
        slot="weapon",
        name="Ember Blade",
        rarity=2,
        atk_permille=200,
    ),
    "thorn_spear": ItemDef(
        id="thorn_spear",
        slot="weapon",
        name="Thorn Spear",
        rarity=1,
        atk_permille=120,
        crit_permille=30,
    ),
    "ion_repeater": ItemDef(
        id="ion_repeater",
        slot="weapon",
        name="Ion Repeater",
        rarity=1,
        atk_permille=100,
        speed_permille=150,
    ),
    "crystal_staff": ItemDef(
        id="crystal_staff",
        slot="weapon",
        name="Crystal Staff",
        rarity=2,
        atk_permille=80,
        crit_permille=140,
    ),
    "void_dagger": ItemDef(
        id="void_dagger",
        slot="weapon",
        name="Void Dagger",
        rarity=3,
        atk_permille=140,
        crit_permille=180,
    ),
    "reinforced_plate": ItemDef(
        id="reinforced_plate",
        slot="armor",
        name="Reinforced Plate",
        rarity=2,
        hp_permille=200,
        damage_reduction_permille=50,
    ),
    "nanofiber_cloak": ItemDef(
        id="nanofiber_cloak",
        slot="armor",
        name="Nanofiber Cloak",
        rarity=1,
        damage_reduction_permille=120,
    ),
    "thorn_mail": ItemDef(
        id="thorn_mail",
        slot="armor",
        name="Thorn Mail",
        rarity=2,
        hp_permille=150,
        damage_reduction_permille=80,
    ),
    "coolant_shell": ItemDef(
        id="coolant_shell",
        slot="armor",
        name="Coolant Shell",
        rarity=2,
        hp_permille=120,
        damage_reduction_permille=120,
    ),
    "medic_vest": ItemDef(
        id="medic_vest",
        slot="armor",
        name="Medic Vest",
        rarity=1,
        hp_permille=100,
        damage_reduction_permille=40,
    ),
    "runic_barrier": ItemDef(
        id="runic_barrier",
        slot="armor",
        name="Runic Barrier",
        rarity=3,
        hp_permille=50,
        damage_reduction_permille=180,
    ),
    "targeting_array": ItemDef(
        id="targeting_array",
        slot="utility",
        name="Targeting Array",
        rarity=1,
        crit_permille=120,
    ),
    "clockwork_core": ItemDef(
        id="clockwork_core",
        slot="utility",
        name="Clockwork Core",
        rarity=1,
        speed_permille=120,
    ),
    "healing_drones": ItemDef(
        id="healing_drones",
        slot="utility",
        name="Healing Drones",
        rarity=1,
        atk_permille=60,
        hp_permille=60,
    ),
    "adrenaline_module": ItemDef(
        id="adrenaline_module",
        slot="utility",
        name="Adrenaline Module",
        rarity=2,
        speed_permille=200,
        crit_permille=30,
    ),
    "smoke_emitter": ItemDef(
        id="smoke_emitter",
        slot="utility",
        name="Smoke Emitter",
        rarity=2,
        damage_reduction_permille=80,
        crit_permille=50,
    ),
    "phoenix_ash": ItemDef(
        id="phoenix_ash",
        slot="utility",
        name="Phoenix Ash",
        rarity=3,
        hp_permille=150,
    ),
    "knight_sigil": ItemDef(
        id="knight_sigil",
        slot="utility",
        name="Knight Sigil",
        rarity=2,
        synergy_bonus={"Knight": 1},
        badge_text="Knight +1",
    ),
    "mech_sigil": ItemDef(
        id="mech_sigil",
        slot="utility",
        name="Mech Sigil",
        rarity=2,
        synergy_bonus={"Mech": 1},
        badge_text="Mech +1",
    ),
    "mystic_sigil": ItemDef(
        id="mystic_sigil",
        slot="utility",
        name="Mystic Sigil",
        rarity=2,
        synergy_bonus={"Mystic": 1},
        badge_text="Mystic +1",
    ),
    "beast_sigil": ItemDef(
        id="beast_sigil",
        slot="utility",
        name="Beast Sigil",
        rarity=2,
        synergy_bonus={"Beast": 1},
        badge_text="Beast +1",
    ),
    "fire_sigil": ItemDef(
        id="fire_sigil",
        slot="utility",
        name="Fire Sigil",
        rarity=3,
        synergy_bonus={"Fire": 2},
        badge_text="Fire +2",
    ),
    "void_sigil": ItemDef(
        id="void_sigil",
        slot="utility",
        name="Void Sigil",
        rarity=3,
        synergy_bonus={"Void": 2},
        badge_text="Void +2",
    ),
}

CREATURES_BY_RARITY: dict[int, list[str]] = {}
for cid, cdef in CREATURES.items():
    CREATURES_BY_RARITY.setdefault(int(cdef.rarity), []).append(cid)
for rarity, ids in CREATURES_BY_RARITY.items():
    ids.sort()

ITEMS_BY_RARITY_SLOT: dict[str, dict[int, list[str]]] = {}
for iid, idef in ITEMS.items():
    slot = str(idef.slot)
    ITEMS_BY_RARITY_SLOT.setdefault(slot, {}).setdefault(int(idef.rarity), []).append(
        iid
    )
for slot, by_rarity in ITEMS_BY_RARITY_SLOT.items():
    for rarity, ids in by_rarity.items():
        ids.sort()


def _tiered(base: dict[str, int]) -> dict[int, dict[str, int]]:
    return {
        2: dict(base),
        4: {k: v * 2 for k, v in base.items()},
        6: {k: v * 3 for k, v in base.items()},
    }


SYNERGY_EFFECTS: dict[str, dict[int, dict[str, int]]] = {
    "Mech": _tiered({"damage_reduction_permille": 100}),
    "Knight": _tiered({"hp_permille": 200}),
    "Mystic": _tiered({"crit_permille": 100}),
    "Beast": _tiered({"atk_permille": 100}),
    "Fire": _tiered({"atk_permille": 50}),
    "Gelatinous": _tiered({"hp_permille": 150}),
    "Heavy": _tiered({"damage_reduction_permille": 80}),
    "Crystal": _tiered({"crit_permille": 120}),
    "Medic": _tiered({"hp_permille": 100, "atk_permille": 50}),
    "Vine": _tiered({"hp_permille": 100, "damage_reduction_permille": 80}),
    "Mist": _tiered({"hp_permille": 120}),
    "Storm": _tiered({"atk_permille": 80}),
    "Void": _tiered({"crit_permille": 200}),
    "Scrap": _tiered({"atk_permille": 60}),
}
