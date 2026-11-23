"""Battle-only elemental resources and placement."""
from .data import ELEMENTALS, SUMMONING, UNITS


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


def summon_plan(state, side, element):
    magic = state.summoning.get(str(side))
    if not magic or element not in magic["elements"]:
        raise ValueError("Цей виклик недоступний.")
    if magic["energy"] < magic["cost"]:
        raise ValueError("Недостатньо енергії для виклику.")
    previous = next((stack for stack in state.stacks.values() if stack.owner == side and stack.summoned), None)
    unit = UNITS[f"elemental_{element}"]
    position = spawn_position(state, unit, previous)
    if position is None:
        raise ValueError("На полі немає місця для елементаля.")
    count, top_hp = squad_health(magic["hp_pool"], unit.hp)
    if not count:
        raise ValueError("Недостатньо сили магії для виклику.")
    return previous, unit, position, count, top_hp


def spell_options(state, side):
    magic = state.summoning.get(str(side))
    if not magic:
        return []
    options = []
    for element in magic["elements"]:
        unit = UNITS[f"elemental_{element}"]
        spell = {
            "element": element, "name": unit.name, "icon": unit.icon, "energy_cost": magic["cost"],
            "description": SUMMONING["description"], "target_label": "Клітинка для союзного загону",
        }
        try:
            _, _, position, _, _ = summon_plan(state, side, element)
            spell["target"] = {"cell": position, "size": unit.size, "side": side}
        except ValueError as exc:
            spell["unavailable"] = str(exc)
        options.append(spell)
    return options
