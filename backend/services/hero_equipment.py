from fastapi import HTTPException
from sqlalchemy import select, update

from backend.models import EquippedItems, Item, User

SLOT_COLUMNS = {
    "head": "helmet", "chest": "armor", "belt": "belt", "legs": "boots",
    "back": "back", "main_hand": "right_hand", "off_hand": "left_hand",
    **{f"acc_{i}": f"jewelry_{i}" for i in range(1, 5)},
}
SLOT_LABELS = {
    "head": "Шолом", "chest": "Броня", "belt": "Пояс", "legs": "Чоботи", "back": "Плащ",
    "main_hand": "Права рука", "off_hand": "Ліва рука",
    **{f"acc_{i}": f"Прикраса {i}" for i in range(1, 5)},
}
ITEM_SLOTS = {
    "helmet": ("head",), "armor": ("chest",), "belt": ("belt",), "boots": ("legs",),
    "back": ("back",), "shield": ("off_hand",),
    "one_handed_weapon": ("main_hand", "off_hand"), "two_handed_weapon": ("main_hand",),
    "jewelry": tuple(f"acc_{i}" for i in range(1, 5)),
}


def equipment_ids(equipped):
    return {slot: getattr(equipped, f"{column}_id") if equipped else None
            for slot, column in SLOT_COLUMNS.items()}


def lock_hero(db, player):
    db.execute(update(User).where(User.id == player.id).values(map_sector=User.map_sector))
    db.refresh(player)


def change_equipment(db, player, *, slot=None, item_id=None, remove=False):
    lock_hero(db, player)
    equipped = player.equipped_items
    ids = equipment_ids(equipped)
    if slot is not None and slot not in SLOT_COLUMNS:
        raise HTTPException(422, "Невідомий слот спорядження.")
    if remove:
        if slot is None:
            slot = next((key for key, value in ids.items() if value == item_id), None)
        if slot is None or ids[slot] is None:
            return
        item_id = ids[slot]
    item = db.scalar(select(Item).where(Item.id == item_id, Item.owner_id == player.id))
    if item is None:
        raise HTTPException(404, "Предмет не знайдено.")
    if remove:
        setattr(equipped, f"{SLOT_COLUMNS[slot]}_id", None)
    else:
        if item.id in ids.values():
            raise HTTPException(409, "Предмет уже екіпіровано.")
        if item.durability is not None and item.durability <= 0:
            raise HTTPException(422, "Зламаний предмет не можна екіпірувати.")
        candidates = ITEM_SLOTS.get(item.item_type, ())
        if slot is None:
            slot = next((key for key in candidates if ids[key] is None), None)
        if slot not in candidates:
            raise HTTPException(422, "Предмет не підходить до цього слота або слот зайнятий.")
        if ids[slot] is not None:
            raise HTTPException(409, "Спочатку звільни цей слот.")
        main = db.get(Item, ids["main_hand"]) if ids["main_hand"] is not None else None
        if ((item.item_type == "two_handed_weapon" and ids["off_hand"] is not None)
                or (slot == "off_hand" and main and main.item_type == "two_handed_weapon")):
            raise HTTPException(409, "Дворучна зброя займає обидві руки.")
        if equipped is None:
            equipped = EquippedItems(user=player)
            db.add(equipped)
        setattr(equipped, f"{SLOT_COLUMNS[slot]}_id", item.id)
    for stat, amount in (item.stats or {}).items():
        if stat in MODIFIED_STATS and isinstance(amount, (int, float)) and not isinstance(amount, bool):
            setattr(player, stat, (getattr(player, stat) or 0) + (-amount if remove else amount))
    item.is_equipped = not remove


MODIFIED_STATS = {
    "stamina", "energy", "agility", "mind", "melee_attack", "ranged_attack", "magic_power",
    "physical_defense", "magic_resistance", "bonus_melee_damage", "bonus_ranged_damage",
    "bonus_magic_damage", "bonus_melee_defense", "bonus_ranged_defense", "bonus_magic_defense",
}
