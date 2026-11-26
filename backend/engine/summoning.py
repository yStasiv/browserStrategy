"""Battle-only elemental resources and placement."""
from .data import ELEMENTALS, SUMMONING, UNITS
from .state import HeroTurn

SPELL_IDS = {"earth": "geolith", "water": "hydro", "air": "aero", "fire": "pyro", "poison": "miasmo", "energy": "volt"}
SPELLS = {
    spell_id: {
        "id": spell_id, "element": element, "name": f"Виклик «{ELEMENTALS[element]['name']}»",
        "school": "summoning", "required_school_level": ELEMENTALS[element]["school_level"],
        "energy_cost": SUMMONING["energy_cost"], "duration_turns": None,
        "icon_url": f"/static/images/spells/spell_{spell_id}.png",
        "short_description": SUMMONING["description"],
        "full_description": (
            "Ельфійський герой викликає елементаля до кінця поточного бою. "
            "Вільний слот армії не потрібен. Новий елементаль замінює попереднього активного елементаля "
            "на стороні героя. Елементаль з’являється на першій вільній клітинці своєї половини поля "
            "під час пошуку згори вниз і зліва направо."
        ),
        "summon_unit_id": f"elemental_{element}",
    }
    for element, spell_id in SPELL_IDS.items()
}


def school_spells(school_level, *, is_elf):
    return [{**spell, "unlocked": is_elf and spell["required_school_level"] <= school_level}
            for spell in SPELLS.values()]


def max_energy(knowledge):
    return max(0, int(SUMMONING["base_energy"] + knowledge * SUMMONING["energy_per_knowledge"]))


def hp_pool(spell_power):
    return max(0, int(SUMMONING["base_hp_pool"] + spell_power * SUMMONING["hp_pool_per_spell_power"]))


def squad_health(total_hp, unit_hp):
    if total_hp <= 0:
        return 0, 0
    full, remainder = divmod(total_hp, unit_hp)
    return full + bool(remainder), remainder or unit_hp


def available_elements(school_level):
    return [key for key, row in ELEMENTALS.items() if row["school_level"] <= school_level]


def spawn_position(state, side, unit, previous):
    occupied = state.blocked_cells(excluding=previous.id if previous else None)
    width, height = unit.size
    midpoint = state.width // 2
    left, right = (0, midpoint) if side == 0 else (midpoint, state.width)
    for y in range(state.height - height + 1):
        for x in range(left, right - width + 1):
            if all((x + dx, y + dy) not in occupied for dx in range(width) for dy in range(height)):
                return x, y
    return None


def summon_plan(state, side, element):
    magic = state.summoning.get(str(side))
    hero = next((hero for hero in state.heroes.values() if hero.owner == side), None)
    if hero and hero.faction != "elves":
        raise ValueError("Цей виклик доступний лише ельфам.")
    if (not magic or element not in ELEMENTALS or element not in magic["elements"]
            or (hero and ELEMENTALS[element]["school_level"] > magic.get("school_level", 0))):
        raise ValueError("Цей виклик недоступний.")
    if magic["energy"] < magic["cost"]:
        raise ValueError("Недостатньо енергії для виклику.")
    previous = next((stack for stack in state.stacks.values() if stack.owner == side and stack.summoned), None)
    unit = UNITS[f"elemental_{element}"]
    position = spawn_position(state, side, unit, previous)
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
    actor = state.active()
    can_act = (state.status == "active" and actor is not None and actor.owner == side
               and (isinstance(actor, HeroTurn) or not state.heroes))
    options = []
    for element in magic["elements"]:
        catalog_entry = SPELLS[SPELL_IDS[element]]
        count, _ = squad_health(magic["hp_pool"], UNITS[catalog_entry["summon_unit_id"]].hp)
        spell = {
            **catalog_entry, "energy_cost": magic["cost"], "can_cast": False, "summon_count": count,
            "description": SUMMONING["description"], "target_label": "Клітинка для союзного загону",
        }
        if not can_act:
            spell["unavailable"] = "Потрібно дочекатися ходу героя."
        else:
            try:
                _, unit, position, _, _ = summon_plan(state, side, element)
                spell["target"] = {"cell": position, "size": unit.size, "side": side}
                spell["can_cast"] = True
            except ValueError as exc:
                spell["unavailable"] = str(exc)
        options.append(spell)
    return options
