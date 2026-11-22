"""Простий ШІ: стріляє / б'є найвигіднішу ціль / підходить ближче. ШІ повертає ту саму Action, що й людина."""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .actions import Attack, Defend, Move
from .rules import apply, dist_stacks, expected_damage, is_ranged, reachable, rect_dist
from .state import BattleState


def choose_action(state: BattleState):
    actor = state.active()
    enemies = [s for s in state.stacks.values() if s.owner != actor.owner]

    if is_ranged(state, actor):
        return Attack(max(enemies, key=lambda e: expected_damage(actor, e, ranged=True)).id)

    dist = reachable(state, actor)
    best = None
    for e in enemies:
        for pos, d in dist.items():
            if rect_dist(pos[0], pos[1], actor.w, actor.h, e.x, e.y, e.w, e.h) == 1:
                score = (expected_damage(actor, e), -d)
                if best is None or score > best[0]:
                    best = (score, e, pos)
    if best:
        _, e, pos = best
        return Attack(e.id, None if pos == (actor.x, actor.y) else pos)

    nearest = min(enemies, key=lambda e: dist_stacks(actor, e))
    pos = min(dist, key=lambda p: (rect_dist(p[0], p[1], actor.w, actor.h, nearest.x, nearest.y, nearest.w, nearest.h),
                                   dist[p]))
    if pos == (actor.x, actor.y):
        return Defend()
    return Move(*pos)


def run_ai(state: BattleState, ai_sides: Iterable[int], max_actions: int = 1000) -> Tuple[BattleState, List[dict]]:
    """Виконує ходи ШІ, доки не настане черга людини або бій не завершиться."""
    ai_sides = set(ai_sides)
    events: List[dict] = []
    for _ in range(max_actions):
        actor = state.active()
        if actor is None or actor.owner not in ai_sides:
            break
        state, ev = apply(state, choose_action(state))
        events += ev
    return state, events
