from fastapi import HTTPException
from sqlalchemy import select, update

from backend import models
from backend.engine.battle_models import ArmySlot
from backend.engine.battle_service import get_active_battle_id, user_level
from backend.engine.data import UNITS, faction_key
from backend.engine.roster import saved_army
from backend.engine.setup import field_rules
from backend.services import castle_buildings


def army_options(db, player, built=None):
    counts = {}
    for key, count in saved_army(db, player.id):
        counts[key] = counts.get(key, 0) + count
    if built is None:
        entries, _ = castle_buildings.catalog()
        built = castle_buildings.built_ids(db, player, entries)
    recruitment_limits = {
        unit.key: unit.recruitment.max_count
        for unit in UNITS.values()
        if unit.recruitment and unit.recruitment.min_level <= user_level(player)
        and unit.recruitment.building in built
        and (not unit.recruitment.factions
             or faction_key(player.fraction) in {faction_key(value) for value in unit.recruitment.factions})
    }
    limits = recruitment_limits.copy()
    for key, count in counts.items():
        limits[key] = max(limits.get(key, 0), count)
    return [
        {"key": key, "name": UNITS[key].name, "unit": UNITS[key], "quantity": counts.get(key, 0),
         "limit": limit, "recruitable": key in recruitment_limits}
        for key, limit in limits.items() if key in UNITS
    ]


def recruitment_cards(options):
    groups = {}
    retained_lines = {
        option["unit"].line for option in options if not option["recruitable"] and option["quantity"]
    }
    for option in options:
        if option["recruitable"]:
            unit = option["unit"]
            groups.setdefault(unit.line or unit.key, []).append(option)
    return [
        {**next((option for option in choices if option["quantity"]), choices[0]),
         "group": key, "choices": choices, "replaces_retained": key in retained_lines}
        for key, choices in groups.items()
    ]


def save_roster(db, player, values, forms=None):
    db.execute(update(models.User).where(models.User.id == player.id).values(map_sector=models.User.map_sector))
    if get_active_battle_id(db, player.id) is not None:
        raise HTTPException(409, "Під час бою склад армії змінити неможливо.")
    options = army_options(db, player)
    limits = {unit["key"]: unit["limit"] for unit in options if unit["recruitable"]}
    groups = {card["group"]: card["choices"] for card in recruitment_cards(options) if card["unit"].line}
    for line, unit_key in (forms or {}).items():
        count_key = f"line:{line}"
        choices = {option["key"] for option in groups.get(line, ())}
        if unit_key not in choices or count_key not in values or choices.intersection(values):
            raise HTTPException(422, "Обери доступну форму істоти.")
        count = values.pop(count_key)
        values.update({key: count if key == unit_key else 0 for key in choices})
    if not values.keys() <= limits.keys() or any(not 0 <= count <= limits[key] for key, count in values.items()):
        raise HTTPException(422, "Вкажи допустиму кількість для кожного загону.")
    replaced_lines = {UNITS[key].line for key, count in values.items() if count and UNITS[key].line}
    army = [(unit["key"], values.get(unit["key"], unit["quantity"])) for unit in options
            if values.get(unit["key"], unit["quantity"])
            and (unit["recruitable"] or unit["unit"].line not in replaced_lines)]
    lines = [UNITS[key].line for key, _ in army if UNITS[key].line]
    if len(set(lines)) != len(lines):
        raise HTTPException(422, "Обери одну форму для кожної лінійки істот.")
    slot_limit = field_rules(user_level(player), "pve").max_slots
    if not 1 <= len(army) <= slot_limit:
        raise HTTPException(422, f"Обери від 1 до {slot_limit} загонів.")
    existing = db.scalars(select(ArmySlot).where(ArmySlot.user_id == player.id)).all()
    by_slot = {entry.slot: entry for entry in existing}
    for index, (key, count) in enumerate(army):
        entry = by_slot.pop(index, None)
        if entry is None:
            db.add(ArmySlot(user_id=player.id, slot=index, unit_key=key, count=count))
        else:
            entry.unit_key, entry.count = key, count
    for entry in by_slot.values():
        db.delete(entry)
    db.commit()
