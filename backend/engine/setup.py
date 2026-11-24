"""Створення бою з двох армій."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from .data import UNITS
from .obstacles import generate_obstacles
from .rules import init_timeline
from .state import HEIGHT_PER_HERO, MAX_SLOTS, WIDTH, BattleState, HeroTurn, Stack

Army = List[Tuple[str, int]]  # [(ключ_істоти, кількість), ...]

LOW_LEVEL_MAX = 3  # рівні 1..3 вважаються низькими
ZONE_COLS = 3      # скільки колонок від краю займає зона розстановки, якщо армія не влазить в одну колонку


@dataclass(frozen=True)
class FieldRules:
    width: int
    height: int
    max_slots: int          # максимум загонів в одній армії


def field_rules(level: int, mode: str, *, heroes_per_side: int = 1) -> FieldRules:
    """Правила поля. Висоту визначає сторона з найбільшою кількістю героїв."""
    if mode not in ("pve", "pvp"):
        raise ValueError(f"невідомий режим: {mode!r}")
    slots = 5 if mode == "pve" and level <= LOW_LEVEL_MAX else MAX_SLOTS
    return FieldRules(width=WIDTH, height=HEIGHT_PER_HERO * max(1, heroes_per_side), max_slots=slots)


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
    left, right = (0, ZONE_COLS) if owner == 0 else (width - ZONE_COLS, width)
    edge_cols = list(range(ZONE_COLS)) if owner == 0 else [width - 1 - i for i in range(ZONE_COLS)]
    for w, h in sizes:
        for col in edge_cols:
            x = col if owner == 0 else col - w + 1
            if x < left or x + w > right:
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
    *, configuration: Optional[FieldRules] = None, heroes: Iterable[HeroTurn] = (),
) -> BattleState:
    """Сторона 0 стає біля лівого краю, сторона 1 — біля правого."""
    heroes = {hero.id: hero for hero in heroes}
    side_counts = Counter(hero.owner for hero in heroes.values())
    rules = configuration or field_rules(level, mode, heroes_per_side=max(side_counts.values(), default=1))
    if rules.width < 1 or rules.height < 1:
        raise ValueError("некоректні розміри поля")
    for army in (army_a, army_b):
        if not army or len(army) > rules.max_slots:
            raise ValueError(f"армія має містити від 1 до {rules.max_slots} загонів")
        for key, count in army:
            if key not in UNITS or count < 1:
                raise ValueError(f"некоректний загін: {key} x{count}")

    height = rules.height
    stacks = {}
    occupied = set()
    for owner, army in ((0, army_a), (1, army_b)):
        sizes = [UNITS[k].size for k, _ in army]
        for i, ((key, count), (w, h), (x, y)) in enumerate(zip(army, sizes, _layout(sizes, owner, rules.width, height))):
            ut = UNITS[key]
            sid = f"s{owner}_{i}"
            stack = Stack(id=sid, unit=key, owner=owner, count=count, top_hp=ut.hp,
                                x=x, y=y, w=w, h=h, shots_left=ut.shots, initial_count=count)
            cells = set(stack.cells())
            if any(not (0 <= x < rules.width and 0 <= y < height) for x, y in cells) or cells & occupied:
                raise ValueError("загони не можна розмістити на цьому полі")
            stacks[sid] = stack
            occupied.update(cells)
    state = BattleState(width=rules.width, height=height, seed=seed, stacks=stacks, heroes=heroes)
    state.obstacles = generate_obstacles(state, ZONE_COLS)
    if state.obstacles:
        state.obstacle_kind = "rock"
    init_timeline(state)
    return state
