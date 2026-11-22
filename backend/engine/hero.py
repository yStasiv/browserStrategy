"""Snapshot a player's off-board combat hero."""
from sqlalchemy import select

from backend.models import Item
from backend.services.hero_attributes import HERO_RULES, hero_attributes
from backend.services.hero_equipment import equipment_ids
from .state import HeroTurn


def make_hero(db, user, side, level):
    ids = set(equipment_ids(user.equipped_items).values()) - {None}
    equipped = db.scalars(select(Item).where(Item.id.in_(ids), Item.owner_id == user.id)).all() if ids else ()
    totals = {key: stat["total"] for key, stat in hero_attributes(user, equipped).items()}
    attack = int(totals["attack"])
    return HeroTurn(
        id=f"hero_{side}", owner=side, name=user.username, level=level, **totals,
        damage_min=max(1, HERO_RULES["damage_min"] + attack),
        damage_max=max(1, HERO_RULES["damage_max"] + attack),
        portrait=user.avatar_url if (user.avatar_url or "").startswith("/avatars/") else None,
    )
