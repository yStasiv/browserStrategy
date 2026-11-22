"""Read the saved roster shared by the castle, character profile and battle."""
from sqlalchemy import select

from .battle_models import ArmySlot


def saved_army(db, player_id):
    slots = db.execute(
        select(ArmySlot.unit_key, ArmySlot.count)
        .where(ArmySlot.user_id == player_id, ArmySlot.count > 0)
        .order_by(ArmySlot.slot)
    )
    return [(key, count) for key, count in slots]
