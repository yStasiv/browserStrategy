"""Оркестрація ходів поверх рушія: хід людини + автоматичні ходи ШІ. Без БД — тому тестується окремо."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

from .actions import action_to_dict
from .events import action_events
from .ai import choose_action
from .rules import IllegalAction, apply, surrender
from .state import BattleState


class NotYourTurn(IllegalAction):
    pass


@dataclass
class Step:
    side: int
    action: dict
    events: List[dict]
    replay_events: List[dict]


def advance_ai(state: BattleState, ai_sides: Iterable[int], max_actions: int = 500) -> Tuple[BattleState, List[Step]]:
    """Виконує ходи ШІ, доки не настане черга людини або бій не завершиться."""
    ai_sides = set(ai_sides)
    steps: List[Step] = []
    for _ in range(max_actions):
        actor = state.active()
        if actor is None or actor.owner not in ai_sides:
            break
        action = choose_action(state)
        previous, (state, events) = state, apply(state, action)
        command = action_to_dict(action)
        steps.append(Step(actor.owner, command, events, action_events(previous, state, events, command)))
    return state, steps


def play_turn(state: BattleState, side: int, action, ai_sides: Iterable[int] = ()) -> Tuple[BattleState, List[Step]]:
    """Дія гравця зі сторони `side`, далі ходи ШІ. Кидає NotYourTurn / IllegalAction."""
    actor = state.active()
    if actor is None:
        raise IllegalAction("бій завершено")
    if actor.owner != side:
        raise NotYourTurn("зараз не ваш хід")
    previous, (state, events) = state, apply(state, action)
    command = action_to_dict(action)
    steps = [Step(side, command, events, action_events(previous, state, events, command))]
    state, ai_steps = advance_ai(state, ai_sides)
    return state, steps + ai_steps


def surrender_turn(state: BattleState, side: int) -> Tuple[BattleState, List[Step]]:
    """Здача: бій одразу завершується, переможцем стає суперник."""
    previous, (state, events) = state, surrender(state, side)
    command = {"type": "surrender"}
    return state, [Step(side, command, events, action_events(previous, state, events, command))]
