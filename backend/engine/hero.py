"""Snapshot a player's off-board combat hero."""
from sqlalchemy import select

from backend.models import Item
from backend.services.combat_effects import active_combat_effects
from backend.services.hero_attributes import HERO_RULES, hero_attributes
from backend.services.hero_equipment import equipment_ids
from .data import faction_key
from .state import HeroTurn


def hero_portrait_url(faction, gender):
    faction = faction_key(faction)
    if faction not in {"elves", "underground_elves"}:
        faction = "elves"
    gender = "female" if gender == "female" else "male"
    return f"/static/images/units_and_buildings/{faction}/hero/{faction}_hero_{gender}.png"


def make_hero(db, user, side, level):
    ids = set(equipment_ids(user.equipped_items).values()) - {None}
    equipped = db.scalars(select(Item).where(Item.id.in_(ids), Item.owner_id == user.id)).all() if ids else ()
    totals = {key: stat["total"] for key, stat in hero_attributes(user, equipped).items()}
    attack = int(totals["attack"])
    return HeroTurn(
        id=f"hero_{side}", owner=side, name=user.username, level=level, **totals,
        damage_min=max(1, HERO_RULES["damage_min"] + attack),
        damage_max=max(1, HERO_RULES["damage_max"] + attack),
        portrait=hero_portrait_url(user.fraction, user.gender),
        faction=faction_key(user.fraction),
        equipment_ids=sorted(item.id for item in equipped),
        combat_effects=active_combat_effects(equipped),
    )
