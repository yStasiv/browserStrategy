"""Створення бою з двох армій."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .data import UNITS
from .obstacles import generate_obstacles
from .rules import init_timeline
from .state import MAX_HEIGHT, MAX_SLOTS, MIN_HEIGHT, WIDTH, BattleState, Stack

Army = List[Tuple[str, int]]  # [(ключ_істоти, кількість), ...]

LOW_LEVEL_MAX = 3  # рівні 1..3 вважаються низькими
ZONE_COLS = 3      # скільки колонок від краю займає зона розстановки, якщо армія не влазить в одну колонку


@dataclass(frozen=True)
class FieldRules:
    width: int
    height: Optional[int]   # None = адаптивна: від MIN_HEIGHT до MAX_HEIGHT за висотою армій
    max_slots: int          # максимум загонів в одній армії


def field_rules(level: int, mode: str) -> FieldRules:
    """Параметри поля й армії залежно від бойового рівня та режиму.

    - PvE, рівні 1-3: поле 8x8, до 5 загонів;
    - PvP (будь-який рівень) і всі бої з 4 рівня: поле 12 в ширину, висота адаптивна, до 8 загонів.
    """
    if mode not in ("pve", "pvp"):
        raise ValueError(f"невідомий режим: {mode!r}")
    if mode == "pve" and level <= LOW_LEVEL_MAX:
        return FieldRules(width=8, height=8, max_slots=5)
    return FieldRules(width=WIDTH, height=None, max_slots=MAX_SLOTS)


def _layout(sizes: List[Tuple[int, int]], owner: int, width: int, height: int) -> List[Tuple[int, int]]:
    """Позиції (лівий верхній кут) для загонів однієї армії.
    Спершу — одна колонка біля краю, по центру вертикалі; якщо висоти не вистачає — розстановка в зоні з кількох колонок."""
    total = sum(h for _, h in sizes)
    if total <= height:
        y = (height - total) // 2
        out = []
        for w, h in sizes:
            out.append((0 if owner == 0 else width - w, y))
            y += h
        return out

    occupied = set()
    out = []
    edge_cols = list(range(ZONE_COLS)) if owner == 0 else [width - 1 - i for i in range(ZONE_COLS)]
    for w, h in sizes:
        for col in edge_cols:
            x = col if owner == 0 else col - w + 1
            if x < 0 or x + w > width:
                continue
            spot = next(((x, y) for y in range(height - h + 1)
                         if not {(x + i, y + j) for i in range(w) for j in range(h)} & occupied), None)
            if spot:
                occupied |= {(spot[0] + i, spot[1] + j) for i in range(w) for j in range(h)}
                out.append(spot)
                break
        else:
            raise ValueError("армія не вміщується на полі")
    return out


def create_battle(
    army_a: Army, army_b: Army, seed: int, level: int = 1, mode: str = "pve",
    *, configuration: Optional[FieldRules] = None,
) -> BattleState:
    """Сторона 0 стає біля лівого краю, сторона 1 — біля правого.
    Висота адаптивного поля = за сумою висот загонів більшої армії (від MIN_HEIGHT до MAX_HEIGHT)."""
    defaults = field_rules(level, mode)
    rules = configuration or defaults
    if rules.width < 1 or (rules.height is not None and rules.height < 1):
        raise ValueError("некоректні розміри поля")
    for army in (army_a, army_b):
        if not army or len(army) > rules.max_slots:
            raise ValueError(f"армія має містити від 1 до {rules.max_slots} загонів")
        for key, count in army:
            if key not in UNITS or count < 1:
                raise ValueError(f"некоректний загін: {key} x{count}")

    def need(army: Army) -> int:
        return sum(UNITS[k].size[1] for k, _ in army)

    height = rules.height or min(MAX_HEIGHT, max(MIN_HEIGHT, need(army_a), need(army_b)))
    stacks = {}
    occupied = set()
    for owner, army in ((0, army_a), (1, army_b)):
        sizes = [UNITS[k].size for k, _ in army]
        for i, ((key, count), (w, h), (x, y)) in enumerate(zip(army, sizes, _layout(sizes, owner, rules.width, height))):
            ut = UNITS[key]
            sid = f"s{owner}_{i}"
            stack = Stack(id=sid, unit=key, owner=owner, count=count, top_hp=ut.hp,
                                x=x, y=y, w=w, h=h, shots_left=ut.shots)
            cells = set(stack.cells())
            if any(not (0 <= x < rules.width and 0 <= y < height) for x, y in cells) or cells & occupied:
                raise ValueError("загони не можна розмістити на цьому полі")
            stacks[sid] = stack
            occupied.update(cells)
    state = BattleState(width=rules.width, height=height, seed=seed, stacks=stacks)
    state.obstacles = generate_obstacles(state, ZONE_COLS)
    if state.obstacles:
        state.obstacle_kind = "rock"
    init_timeline(state)
    return state
