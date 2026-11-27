"""Стан бою. Усе серіалізується в JSON (to_dict / from_dict) для збереження в БД.

Раундів немає: черга ходів безперервна (шкала готовності). Кожен загін має `ready` —
момент, коли він діятиме наступного разу. Діє той, у кого `ready` найменший;
після дії `ready` зростає на «період» загону (чим вища ініціатива, тим він коротший)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from itertools import chain
from typing import Dict, List, Optional, Tuple

WIDTH = 12
HEIGHT_PER_HERO = 10
MAX_SLOTS = 8       # абсолютний максимум слотів армії на сторону
MAX_ACTIONS = 600   # після такої кількості дій бій завершується нічиєю (захист від вічного бою)
ATB_SCALE = 100_000 # період загону = ATB_SCALE // ініціатива


def compact_stack_snapshot(data):
    if not data["summoned"]:
        del data["summoned"]
    for key in ("initial_count", "luck", "morale", "energy", "max_energy"):
        if data[key] is None:
            del data[key]
    for key in ("luck_streak", "morale_streak"):
        if data[key] == 1:
            del data[key]
    return data


@dataclass
class Stack:
    id: str
    unit: str          # ключ з data.UNITS
    owner: int         # сторона: 0 або 1
    count: int
    top_hp: int        # HP верхньої істоти в загоні
    x: int             # лівий верхній кут загону
    y: int
    w: int = 1         # розмір у клітинках (ширина x висота)
    h: int = 1
    ready: int = 0     # коли діятиме наступного разу
    shots_left: int = 0
    defending: bool = False
    waited: bool = False       # Сумісність зі знімками боїв зі старим правилом очікування.
    retaliated: bool = False   # вже контратакував з початку свого останнього ходу
    summoned: bool = False
    initial_count: int | None = None
    luck: float | None = None
    morale: float | None = None
    luck_streak: int = 1
    morale_streak: int = 1
    energy: int | None = None
    max_energy: int | None = None
    combat_effects: dict[str, float] = field(default_factory=dict)

    def cells(self) -> List[Tuple[int, int]]:
        return [(self.x + i, self.y + j) for i in range(self.w) for j in range(self.h)]


@dataclass
class HeroTurn:
    id: str
    owner: int
    name: str
    level: int
    initiative: int
    attack: int | float
    defense: int | float
    knowledge: int | float
    spell_power: int | float
    damage_min: int
    damage_max: int
    luck: int | float = 0
    morale: int | float = 0
    ready: int = 0
    portrait: str | None = None
    faction: str | None = None
    equipment_ids: list[int] = field(default_factory=list)
    combat_effects: dict[str, float] = field(default_factory=dict)


@dataclass
class BattleState:
    width: int
    height: int
    seed: int
    stacks: Dict[str, Stack]
    active_id: Optional[str] = None     # загін або герой, що діє зараз
    seq: int = 0                        # скільки дій виконано
    status: str = "active"              # active | finished
    winner: Optional[int] = None        # None при нічиїй
    surrendered: Optional[int] = None   # сторона, що здалася

    hunt_key: Optional[str] = None
    hunt_level: Optional[int] = None
    summoning: Dict[str, dict] = field(default_factory=dict)
    heroes: Dict[str, HeroTurn] = field(default_factory=dict)
    initial_ready_at: Dict[str, int] = field(default_factory=dict)
    placed_stack_ids: List[str] = field(default_factory=list)
    obstacles: List[List[int]] = field(default_factory=list)
    obstacle_kind: str | None = None

    def blocked_cells(self, *, excluding: str | None = None) -> set[Tuple[int, int]]:
        return {tuple(cell) for cell in self.obstacles} | {
            cell for stack in self.stacks.values() if stack.id != excluding for cell in stack.cells()
        }

    def actors(self):
        return chain(self.stacks.values(), self.heroes.values())

    def active(self) -> Stack | HeroTurn | None:
        if self.status != "active" or self.active_id is None:
            return None
        return self.stacks.get(self.active_id) or self.heroes[self.active_id]

    def stack_at(self, x: int, y: int) -> Optional[Stack]:
        for s in self.stacks.values():
            if (x, y) in s.cells():
                return s
        return None

    def to_dict(self) -> dict:
        snapshot = asdict(self)
        if self.obstacle_kind is None:
            del snapshot["obstacle_kind"]
        if not self.obstacles:
            del snapshot["obstacles"]
        if not self.placed_stack_ids:
            del snapshot["placed_stack_ids"]
        if not self.initial_ready_at:
            del snapshot["initial_ready_at"]
        if self.hunt_key is None:
            del snapshot["hunt_key"]
        if self.hunt_level is None:
            del snapshot["hunt_level"]
        if not self.summoning:
            del snapshot["summoning"]
        if not self.heroes:
            del snapshot["heroes"]
        else:
            for hero in snapshot["heroes"].values():
                if hero["portrait"] is None:
                    del hero["portrait"]
                if hero["faction"] is None:
                    del hero["faction"]
                if not hero["equipment_ids"]:
                    del hero["equipment_ids"]
        for stack in snapshot["stacks"].values():
            compact_stack_snapshot(stack)
        return snapshot

    @classmethod
    def from_dict(cls, d: dict) -> "BattleState":
        known = {f.name for f in fields(cls)}
        sfields = {f.name for f in fields(Stack)}
        d = {k: v for k, v in d.items() if k in known}   # старі/зайві ключі ігноруємо
        d["stacks"] = {k: Stack(**{a: b for a, b in v.items() if a in sfields})
                       for k, v in d["stacks"].items()}
        d["heroes"] = {key: HeroTurn(**value) for key, value in d.get("heroes", {}).items()}
        return cls(**d)
