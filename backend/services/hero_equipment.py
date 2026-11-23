from fastapi import HTTPException
from sqlalchemy import select, update

from backend.models import EquippedItems, Item, User

INVENTORY_LIMIT = 30
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
    "helmet": ("head",), "armor": ("chest",), "armor:": ("chest",), "belt": ("belt",), "boots": ("legs",),
    "back": ("back",), "shield": ("off_hand",),
    "one_handed_weapon": ("main_hand", "off_hand"), "two_handed_weapon": ("main_hand",), "bow": ("off_hand",),
    "jewelry": tuple(f"acc_{i}" for i in range(1, 5)),
}
TWO_HANDED_TYPES = {"two_handed_weapon"}


def hand_conflict(item_type, slot, ids, main_type):
    return ((item_type in TWO_HANDED_TYPES and ids["off_hand"] is not None)
            or (slot == "off_hand" and main_type in TWO_HANDED_TYPES))


def equipment_ids(equipped):
    return {slot: getattr(equipped, f"{column}_id") if equipped else None
            for slot, column in SLOT_COLUMNS.items()}


def lock_hero(db, player):
    db.execute(update(User).where(User.id == player.id).values(map_sector=User.map_sector))
    db.refresh(player)


def apply_equipment(equipped, player, slot, item, worn):
    setattr(equipped, f"{SLOT_COLUMNS[slot]}_id", item.id if worn else None)
    for stat, amount in (item.stats or {}).items():
        if stat in MODIFIED_STATS and type(amount) in (int, float):
            setattr(player, stat, (getattr(player, stat) or 0) + (amount if worn else -amount))
    item.is_equipped = worn


def change_equipment(db, player, *, slot=None, item_id=None, remove=False, replace=False):
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
        apply_equipment(equipped, player, slot, item, False)
    else:
        level = item.level_required
        if player.level < level:
            raise HTTPException(422, {"code": "artifact_level", "message": f"Необхідний рівень {level}."})
        if item.id in ids.values():
            raise HTTPException(409, "Предмет уже екіпіровано.")
        if item.durability is not None and item.durability <= 0:
            raise HTTPException(422, "Зламаний предмет не можна екіпірувати.")
        candidates = ITEM_SLOTS.get(item.item_type, ())
        main = db.get(Item, ids["main_hand"]) if ids["main_hand"] is not None else None
        main_type = main.item_type if main else None
        if slot is None:
            slot = next((key for key in candidates if ids[key] is None
                         and not hand_conflict(item.item_type, key, ids, main_type)), None)
            if slot is None and candidates:
                slot = candidates[0]
        if slot not in candidates:
            raise HTTPException(422, "Предмет не підходить до цього слота або слот зайнятий.")
        if ids[slot] is not None and not replace:
            raise HTTPException(409, "Спочатку звільни цей слот.")
        conflict = hand_conflict(item.item_type, slot, ids, main_type)
        if conflict and not replace:
            raise HTTPException(409, "Дворучна зброя займає обидві руки.")
        if equipped is None:
            equipped = EquippedItems(user=player)
            db.add(equipped)
        if replace:
            displaced = [slot]
            if conflict:
                displaced.append("main_hand" if slot == "off_hand" else "off_hand")
            for key in displaced:
                if ids[key] is not None:
                    previous = db.get(Item, ids[key])
                    if previous is not None and previous.owner_id == player.id:
                        apply_equipment(equipped, player, key, previous, False)
                    else:
                        setattr(equipped, f"{SLOT_COLUMNS[key]}_id", None)
        apply_equipment(equipped, player, slot, item, True)


MODIFIED_STATS = {
    "stamina", "energy", "agility", "mind", "melee_attack", "ranged_attack", "magic_power",
    "physical_defense", "magic_resistance", "bonus_melee_damage", "bonus_ranged_damage",
    "bonus_magic_damage", "bonus_melee_defense", "bonus_ranged_defense", "bonus_magic_defense",
}
