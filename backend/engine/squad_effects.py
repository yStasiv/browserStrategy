"""Squad combat rolls and HP restoration, independent of spell sources."""
from dataclasses import asdict
from random import Random

from .data import UNITS
from .state import Stack, compact_stack_snapshot


def squad_stat(state, stack, stat):
    stored = getattr(stack, stat)
    if stored is not None:
        return stored
    hero = next((hero for hero in state.heroes.values() if hero.owner == stack.owner), None)
    return getattr(UNITS[stack.unit], stat) + (getattr(hero, stat) if hero else 0)


def roll_squad_stat(state, stack, stat, events):
    value = squad_stat(state, stack, stat)
    if not value:
        return 0
    counter = f"{stat}_streak"
    streak = getattr(stack, counter)
    chance = min(100, abs(value) * 5 * streak)
    roll = Random(f"{state.seed}:{state.seq}:{stack.id}:{stat}").random() * 100
    direction = (1 if value > 0 else -1) if roll < chance else 0
    next_streak = 1 if direction else streak + 1
    setattr(stack, counter, next_streak)
    outcome = "positive" if direction > 0 else "negative" if direction < 0 else "none"
    events.append({
        "type": stat, "stack": stack.id, "stat": value, "roll": roll, "chance": chance,
        "streak_before": streak, "streak_after": next_streak, "outcome": outcome,
        "animation_event": bool(direction), "anim_type": f"{outcome}_{stat}" if direction else None,
    })
    return direction


def total_hp(stack: Stack) -> int:
    return (stack.count - 1) * UNITS[stack.unit].hp + stack.top_hp if stack.count > 0 else 0


def heal_squad(stack: Stack, amount: int, *, allow_resurrect=False, events=None) -> int:
    """Restore HP to a retained squad, optionally reviving units up to its start count.

    A source that revives a destroyed squad must retain the squad and choose a legal
    placement before returning it to the field.
    """
    if type(amount) is not int or amount < 0:
        raise ValueError("Лікування має бути невід’ємним цілим числом.")
    hp = UNITS[stack.unit].hp
    count_before = stack.count
    hp_before = total_hp(stack)
    limit = stack.initial_count if stack.initial_count is not None else count_before
    ceiling = (limit if allow_resurrect else count_before) * hp
    hp_after = min(ceiling, hp_before + amount)
    if hp_after <= hp_before:
        return 0
    stack.count = (hp_after + hp - 1) // hp
    stack.top_hp = hp_after - (stack.count - 1) * hp
    if events is not None:
        events.append({
            "type": "heal", "target": stack.id, "healed": hp_after - hp_before,
            "resurrected": stack.count - count_before, "hp_before": hp_before, "hp_after": hp_after,
            "target_count_after": stack.count, "top_hp": stack.top_hp,
            **({"stack_after": compact_stack_snapshot(asdict(stack))} if not count_before else {}),
        })
    return hp_after - hp_before
