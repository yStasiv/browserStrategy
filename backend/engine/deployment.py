from collections import Counter
from dataclasses import replace

from .setup import ZONE_COLS, _layout, field_rules


def slot_limit(level, mode):
    return field_rules(level, mode).max_slots


def place(state, side, stack_id, x, y, *, ai_sides):
    stack = state.stacks.get(stack_id)
    if stack is None or stack.owner != side:
        raise ValueError("Можна розставляти лише свої загони.")

    left = 0 if side == 0 else state.width - ZONE_COLS
    right = left + ZONE_COLS
    if not (left <= x and x + stack.w <= right and 0 <= y and y + stack.h <= state.height):
        raise ValueError("Загін має повністю поміститися у своїй зоні розстановки.")
    placed = replace(stack, x=x, y=y)
    occupied = {tuple(cell) for cell in state.obstacles}
    occupied.update(
        cell for other in state.stacks.values()
        if other.id != stack_id and (other.owner in ai_sides or other.id in state.placed_stack_ids)
        for cell in other.cells()
    )
    if occupied.intersection(placed.cells()):
        raise ValueError("Ці клітинки зайняті.")
    state.stacks[stack_id] = placed
    if stack_id not in state.placed_stack_ids:
        state.placed_stack_ids.append(stack_id)


def split(state, side, stack_id, count, *, limit):
    stack = state.stacks.get(stack_id)
    if stack is None or stack.owner != side:
        raise ValueError("Можна ділити лише свої загони.")
    if not 0 < count < stack.count:
        raise ValueError("Залиши хоча б одну істоту в кожному загоні.")
    if sum(other.owner == side for other in state.stacks.values()) >= limit:
        raise ValueError("Усі слоти загонів зайняті.")
    index = next(i for i in range(limit) if f"s{side}_{i}" not in state.stacks)
    new_id = f"s{side}_{index}"
    state.stacks[new_id] = replace(stack, id=new_id, x=-1, y=-1, count=count, initial_count=count)
    stack.count -= count
    stack.initial_count = stack.count


def unplaced_stacks(state, human_sides):
    placed = set(state.placed_stack_ids)
    return [stack for stack in state.stacks.values() if stack.owner in human_sides and stack.id not in placed]


def merge(state, side, source_id, target_id):
    source = state.stacks.get(source_id)
    target = state.stacks.get(target_id)
    if source is None or target is None or source.owner != side or target.owner != side:
        raise ValueError("Можна об’єднувати лише свої загони.")
    if source_id == target_id or source.unit != target.unit:
        raise ValueError("Обери інший загін тієї самої форми істоти.")

    target.count += source.count
    target.initial_count = target.count
    del state.stacks[source_id]
    state.initial_ready_at.pop(source_id, None)
    if source_id in state.placed_stack_ids:
        state.placed_stack_ids.remove(source_id)


def arrange(state, side, previous, *, limit, ai_sides):
    own = [stack for stack in state.stacks.values() if stack.owner == side]

    def assign(entries):
        arranged = replace(
            state,
            stacks={key: stack for key, stack in state.stacks.items() if stack.owner != side},
            placed_stack_ids=[key for key in state.placed_stack_ids if state.stacks[key].owner != side],
        )
        for stack, x, y in entries:
            arranged.stacks[stack.id] = stack
            place(arranged, side, stack.id, x, y, ai_sides=ai_sides)
        return arranged

    if previous:
        snapshot, previous_side = previous
        saved = [stack for stack in snapshot["stacks"].values()
                 if stack["owner"] == previous_side and not stack.get("summoned")]
        current_totals, saved_totals = Counter(), Counter()
        for stack in own:
            current_totals[stack.unit] += stack.count
        for stack in saved:
            saved_totals[stack["unit"]] += stack["count"]
        if saved and len(saved) <= limit and current_totals == saved_totals:
            templates = {stack.unit: stack for stack in own}
            formation = []
            for index, row in enumerate(saved):
                stack = templates[row["unit"]]
                count = row["count"]
                edge = row["x"] if previous_side == 0 else snapshot["width"] - row["x"] - stack.w
                x = edge if side == 0 else state.width - edge - stack.w
                formation.append((replace(stack, id=f"s{side}_{index}", count=count, initial_count=count), x, row["y"]))
            try:
                return assign(formation), True
            except ValueError:
                pass

    positions = _layout([(stack.w, stack.h) for stack in own], side, state.width, state.height)
    return assign((stack, x, y) for stack, (x, y) in zip(own, positions)), False
