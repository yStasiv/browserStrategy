"""Battle-only elemental resources and placement."""
from .data import ELEMENTALS, SUMMONING


def max_energy(knowledge):
    return SUMMONING["base_energy"] + max(0, int(knowledge)) * SUMMONING["energy_per_knowledge"]


def hp_pool(spell_power):
    return SUMMONING["base_hp_pool"] + max(0, int(spell_power)) * SUMMONING["hp_pool_per_spell_power"]


def squad_health(total_hp, unit_hp):
    if total_hp <= 0:
        return 0, 0
    full, remainder = divmod(total_hp, unit_hp)
    return full + bool(remainder), remainder or unit_hp


def available_elements(school_level):
    return [key for key, row in ELEMENTALS.items() if row["school_level"] <= school_level]


def spawn_position(state, unit, previous):
    occupied = {
        cell for stack in state.stacks.values() if stack is not previous for cell in stack.cells()
    }
    width, height = unit.size
    for y in range(state.height - height + 1):
        for x in range(state.width - width + 1):
            if all((x + dx, y + dy) not in occupied for dx in range(width) for dy in range(height)):
                return x, y
    return None
