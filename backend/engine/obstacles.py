"""Seeded arena obstacles that preserve routes for every squad footprint."""
from dataclasses import replace
from random import Random

from .rules import reachable


def _connected(width, height, size, obstacles):
    """Check orthogonal connectivity of all legal positions for a footprint."""
    w, h = size
    free = {
        (x, y) for y in range(height - h + 1) for x in range(width - w + 1)
        if all((x + dx, y + dy) not in obstacles for dx in range(w) for dy in range(h))
    }
    if not free:
        return False
    frontier = [free.pop()]
    while frontier:
        x, y = frontier.pop()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in free:
                free.remove(neighbor)
                frontier.append(neighbor)
    return not free


def generate_obstacles(state, zone_width):
    """Add sparse single-cell rocks outside deployment zones and occupied tiles."""
    occupied = state.blocked_cells()
    candidates = [
        (x, y) for y in range(state.height) for x in range(zone_width, state.width - zone_width)
        if (x, y) not in occupied
    ]
    if not candidates:
        return []

    rng = Random(f"{state.seed}:obstacles")
    rng.shuffle(candidates)
    area = state.width * state.height
    count = min(rng.randint(max(1, area // 32), max(1, area // 20)), max(1, len(candidates) // 4))
    footprints = {(stack.w, stack.h) for stack in state.stacks.values()} | {(1, 1)}
    movable = [stack for stack in state.stacks.values() if len(reachable(state, stack)) > 1]
    obstacles = set()
    for cell in candidates:
        proposed = obstacles | {cell}
        if not all(_connected(state.width, state.height, size, proposed) for size in footprints):
            continue
        arena = replace(state, obstacles=[list(cell) for cell in proposed])
        if any(len(reachable(arena, stack)) == 1 for stack in movable):
            continue
        obstacles.add(cell)
        if len(obstacles) == count:
            break
    return [list(cell) for cell in sorted(obstacles)]
