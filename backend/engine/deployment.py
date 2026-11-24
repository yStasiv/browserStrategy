from dataclasses import replace

from .setup import ZONE_COLS, field_rules


def slot_limit(level, mode):
    return field_rules(level, mode).max_slots


def place(state, side, stack_id, x, y, split_count, limit):
    stack = state.stacks.get(stack_id)
    if stack is None or stack.owner != side:
        raise ValueError("Можна розставляти лише свої загони.")
    splitting = split_count is not None
    if splitting and not 0 < split_count < stack.count:
        raise ValueError("Залиши хоча б одну істоту в кожному загоні.")
    if splitting and sum(s.owner == side for s in state.stacks.values()) >= limit:
        raise ValueError("Усі слоти загонів зайняті.")

    left = 0 if side == 0 else state.width - ZONE_COLS
    right = left + ZONE_COLS
    if not (left <= x and x + stack.w <= right and 0 <= y and y + stack.h <= state.height):
        raise ValueError("Загін має повністю поміститися у своїй зоні розстановки.")
    placed = replace(stack, x=x, y=y)
    if state.blocked_cells(excluding=None if splitting else stack.id).intersection(placed.cells()):
        raise ValueError("Ці клітинки зайняті.")
    if splitting:
        index = next(i for i in range(limit) if f"s{side}_{i}" not in state.stacks)
        placed = replace(placed, id=f"s{side}_{index}", count=split_count)
        stack.count -= split_count
    state.stacks[placed.id] = placed
    if placed.id not in state.placed_stack_ids:
        state.placed_stack_ids.append(placed.id)
