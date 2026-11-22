"""Стан бою. Усе серіалізується в JSON (to_dict / from_dict) для збереження в БД.

Раундів немає: черга ходів безперервна (шкала готовності). Кожен загін має `ready` —
момент, коли він діятиме наступного разу. Діє той, у кого `ready` найменший;
після дії `ready` зростає на «період» загону (чим вища ініціатива, тим він коротший)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Dict, List, Optional, Tuple

WIDTH = 12          # ширина поля (великі бої)
MIN_HEIGHT = 5      # мінімальна висота адаптивного поля
MAX_HEIGHT = 12     # максимальна висота адаптивного поля
MAX_SLOTS = 8       # абсолютний максимум слотів армії на сторону
MAX_ACTIONS = 600   # після такої кількості дій бій завершується нічиєю (захист від вічного бою)
ATB_SCALE = 100_000 # період загону = ATB_SCALE // ініціатива


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
    waited: bool = False       # «чекати» можна один раз за весь бій
    retaliated: bool = False   # вже контратакував з початку свого останнього ходу
    summoned: bool = False

    def cells(self) -> List[Tuple[int, int]]:
        return [(self.x + i, self.y + j) for i in range(self.w) for j in range(self.h)]


@dataclass
class BattleState:
    width: int
    height: int
    seed: int
    stacks: Dict[str, Stack]
    active_id: Optional[str] = None     # загін, що діє зараз
    seq: int = 0                        # скільки дій виконано
    status: str = "active"              # active | finished
    winner: Optional[int] = None        # None при нічиїй
    surrendered: Optional[int] = None   # сторона, що здалася

    hunt_key: Optional[str] = None
    summoning: Dict[str, dict] = field(default_factory=dict)

    def active(self) -> Optional[Stack]:
        if self.status != "active" or self.active_id is None:
            return None
        return self.stacks[self.active_id]

    def stack_at(self, x: int, y: int) -> Optional[Stack]:
        for s in self.stacks.values():
            if (x, y) in s.cells():
                return s
        return None

    def to_dict(self) -> dict:
        snapshot = asdict(self)
        if self.hunt_key is None:
            del snapshot["hunt_key"]
        if not self.summoning:
            del snapshot["summoning"]
        for stack in snapshot["stacks"].values():
            if not stack["summoned"]:
                del stack["summoned"]
        return snapshot

    @classmethod
    def from_dict(cls, d: dict) -> "BattleState":
        known = {f.name for f in fields(cls)}
        sfields = {f.name for f in fields(Stack)}
        d = {k: v for k, v in d.items() if k in known}   # старі/зайві ключі ігноруємо
        d["stacks"] = {k: Stack(**{a: b for a, b in v.items() if a in sfields})
                       for k, v in d["stacks"].items()}
        return cls(**d)
