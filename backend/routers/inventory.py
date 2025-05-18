from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import database, models
from backend.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/inventory")
async def get_inventory(request: Request, db: Session = Depends(database.get_db)):
    player = await get_current_user(request, db)
    if not player:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Отримуємо всі вдягнені предмети
    equipped_items = {}
    if player.equipped_items:
        slots = {
            "helmet_id": "Шолом",
            "armor_id": "Броня",
            "boots_id": "Чоботи",
            "right_hand_id": "Права рука",
            "left_hand_id": "Ліва рука",
            "back_id": "Спина",
            "jewelry_1_id": "Прикраса 1",
            "jewelry_2_id": "Прикраса 2",
            "jewelry_3_id": "Прикраса 3",
            "jewelry_4_id": "Прикраса 4",
        }

        for slot_id, slot_name in slots.items():
            item_id = getattr(player.equipped_items, slot_id)
            if item_id:
                item = db.query(models.Item).filter(models.Item.id == item_id).first()
                if item:
                    equipped_items[slot_name] = item

    # Оновлені бонуси від предметів
    user_data = {
        # Основні характеристики
        "stamina": player.stamina or 0,
        "stamina_bonus": sum(
            item.stats.get("stamina", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "energy": player.energy or 0,
        "energy_bonus": sum(
            item.stats.get("energy", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "agility": player.agility or 0,
        "agility_bonus": sum(
            item.stats.get("agility", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "mind": player.mind or 0,
        "mind_bonus": sum(
            item.stats.get("mind", 0) for item in equipped_items.values() if item.stats
        ),
        # Додаткові характеристики
        "melee_attack": player.melee_attack or 0,
        "melee_attack_bonus": sum(
            item.stats.get("melee_attack", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "ranged_attack": player.ranged_attack or 0,
        "ranged_attack_bonus": sum(
            item.stats.get("ranged_attack", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "magic_power": player.magic_power or 0,
        "magic_power_bonus": sum(
            item.stats.get("magic_power", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "physical_defense": player.physical_defense or 0,
        "physical_defense_bonus": sum(
            item.stats.get("physical_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "magic_resistance": player.magic_resistance or 0,
        "magic_resistance_bonus": sum(
            item.stats.get("magic_resistance", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        # Бонуси до шкоди
        "bonus_melee_damage": player.bonus_melee_damage or 0,
        "bonus_melee_damage_bonus": sum(
            item.stats.get("bonus_melee_damage", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_ranged_damage": player.bonus_ranged_damage or 0,
        "bonus_ranged_damage_bonus": sum(
            item.stats.get("bonus_ranged_damage", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_magic_damage": player.bonus_magic_damage or 0,
        "bonus_magic_damage_bonus": sum(
            item.stats.get("bonus_magic_damage", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        # Бонуси до захисту
        "bonus_melee_defense": player.bonus_melee_defense or 0,
        "bonus_melee_defense_bonus": sum(
            item.stats.get("bonus_melee_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_ranged_defense": player.bonus_ranged_defense or 0,
        "bonus_ranged_defense_bonus": sum(
            item.stats.get("bonus_ranged_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_magic_defense": player.bonus_magic_defense or 0,
        "bonus_magic_defense_bonus": sum(
            item.stats.get("bonus_magic_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
    }

    inventory_items = (
        db.query(models.Item)
        .filter(models.Item.owner_id == player.id, models.Item.is_equipped == False)
        .all()
    )

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "player": user_data,
            "inventory_items": inventory_items,
            "equipped_items": equipped_items,
            "max_items": 30,
        },
    )


@router.post("/inventory/equip/{item_id}")
async def equip_item(
    item_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    slot: str = None,
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    item = (
        db.query(models.Item)
        .filter(models.Item.id == item_id, models.Item.owner_id == user.id)
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Перевіряємо durability з урахуванням None
    if item.durability is not None and item.durability <= 0:
        raise HTTPException(
            status_code=400, detail="Item is broken and cannot be equipped"
        )

    # Отримуємо або створюємо equipped_items
    equipped = user.equipped_items or models.EquippedItems(user_id=user.id)
    if not user.equipped_items:
        db.add(equipped)

    # Логіка для зброї
    if item.item_type in ["one_handed_weapon", "two_handed_weapon"]:
        # Перевірка для дворучної зброї
        if item.item_type == "two_handed_weapon":
            if equipped.right_hand_id or equipped.left_hand_id:
                raise HTTPException(
                    status_code=400,
                    detail="Unequip all weapons before equipping two-handed weapon",
                )
            equipped.right_hand_id = item.id
            equipped.left_hand_id = None
        # Логіка для одноручної зброї
        else:
            if equipped.right_hand_id and equipped.right_hand_id == item.id:
                raise HTTPException(
                    status_code=400, detail="This weapon is already equipped"
                )

            # Перевіряємо чи не вдягнена дворучна зброя
            right_hand = (
                db.query(models.Item).filter_by(id=equipped.right_hand_id).first()
            )
            if right_hand and right_hand.item_type == "two_handed_weapon":
                raise HTTPException(
                    status_code=400, detail="Unequip two-handed weapon first"
                )

            # Вдягаємо в конкретний слот або в перший вільний
            if slot == "left_hand":
                if equipped.left_hand_id:
                    raise HTTPException(status_code=400, detail="Left hand is occupied")
                equipped.left_hand_id = item.id
            elif slot == "right_hand":
                if equipped.right_hand_id:
                    raise HTTPException(
                        status_code=400, detail="Right hand is occupied"
                    )
                equipped.right_hand_id = item.id
            else:
                # Якщо слот не вказано, вдягаємо в перший вільний
                if not equipped.right_hand_id:
                    equipped.right_hand_id = item.id
                elif not equipped.left_hand_id:
                    equipped.left_hand_id = item.id
                else:
                    raise HTTPException(
                        status_code=400, detail="Both hands are occupied"
                    )

    # Логіка для інших типів предметів залишається без змін
    elif item.item_type == "jewelry":
        if not equipped.jewelry_1_id:
            equipped.jewelry_1_id = item.id
        elif not equipped.jewelry_2_id:
            equipped.jewelry_2_id = item.id
        elif not equipped.jewelry_3_id:
            equipped.jewelry_3_id = item.id
        elif not equipped.jewelry_4_id:
            equipped.jewelry_4_id = item.id
        else:
            raise HTTPException(
                status_code=400, detail="All jewelry slots are occupied"
            )
    else:
        # Для інших типів предметів
        if item.item_type == "helmet":
            if equipped.helmet_id:
                raise HTTPException(status_code=400, detail="Helmet slot is occupied")
            equipped.helmet_id = item.id
        elif item.item_type == "armor":
            if equipped.armor_id:
                raise HTTPException(status_code=400, detail="Armor slot is occupied")
            equipped.armor_id = item.id
        elif item.item_type == "boots":
            if equipped.boots_id:
                raise HTTPException(status_code=400, detail="Boots slot is occupied")
            equipped.boots_id = item.id
        elif item.item_type == "back":
            if equipped.back_id:
                raise HTTPException(status_code=400, detail="Back slot is occupied")
            equipped.back_id = item.id

    # Оновлюємо статистику користувача
    if item.stats:
        for stat, value in item.stats.items():
            if hasattr(user, stat):
                current_value = getattr(user, stat) or 0
                setattr(user, stat, current_value + value)

    item.is_equipped = True
    db.commit()
    return {"status": "success"}


@router.post("/inventory/unequip/{item_id}")
async def unequip_item(
    item_id: int, request: Request, db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    item = (
        db.query(models.Item)
        .filter(
            models.Item.id == item_id,
            models.Item.owner_id == user.id,
            models.Item.is_equipped == True,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Equipped item not found")

    equipped = user.equipped_items
    if not equipped:
        raise HTTPException(status_code=400, detail="No equipped items")

    # Знімаємо бонуси предмета
    if item.stats:
        for stat, value in item.stats.items():
            if hasattr(user, stat):
                current_value = getattr(user, stat) or 0
                new_value = max(0, current_value - value)
                setattr(user, stat, new_value)

    # Знімаємо предмет з відповідного слота
    if item.item_type == "two_handed_weapon":
        equipped.right_hand_id = None
        equipped.left_hand_id = None
    elif item.item_type == "one_handed_weapon":
        if equipped.right_hand_id == item.id:
            equipped.right_hand_id = None
        else:
            equipped.left_hand_id = None
    elif item.item_type == "jewelry":
        if equipped.jewelry_1_id == item.id:
            equipped.jewelry_1_id = None
        elif equipped.jewelry_2_id == item.id:
            equipped.jewelry_2_id = None
        elif equipped.jewelry_3_id == item.id:
            equipped.jewelry_3_id = None
        elif equipped.jewelry_4_id == item.id:
            equipped.jewelry_4_id = None
    elif item.item_type == "helmet":
        equipped.helmet_id = None
    elif item.item_type == "armor":
        equipped.armor_id = None
    elif item.item_type == "boots":
        equipped.boots_id = None
    elif item.item_type == "back":
        equipped.back_id = None

    item.is_equipped = False
    db.commit()
    return {"status": "success"}


@router.post("/inventory/destroy/{item_id}")
async def destroy_item(
    item_id: int, request: Request, db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    item = (
        db.query(models.Item)
        .filter(models.Item.id == item_id, models.Item.owner_id == user.id)
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Якщо предмет вдягнений, знімаємо його бонуси
    if item.is_equipped:
        if item.stats:
            for stat, value in item.stats.items():
                if hasattr(user, stat):
                    current_value = getattr(user, stat)
                    setattr(user, stat, current_value - value)

        # Очищаємо слот спорядження
        equipped = user.equipped_items
        if equipped:
            for slot in [
                "helmet_id",
                "armor_id",
                "boots_id",
                "right_hand_id",
                "left_hand_id",
                "back_id",
                "jewelry_1_id",
                "jewelry_2_id",
                "jewelry_3_id",
                "jewelry_4_id",
            ]:
                if getattr(equipped, slot) == item.id:
                    setattr(equipped, slot, None)

    # Видаляємо предмет
    db.delete(item)
    db.commit()

    return {"status": "success"}


@router.get("/inventory/stats")
async def get_stats(request: Request, db: Session = Depends(database.get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        # Основні характеристики
        "stamina": user.stamina or 0,
        "energy": user.energy or 0,
        "agility": user.agility or 0,
        "mind": user.mind or 0,
        # Додаткові характеристики
        "melee_attack": user.melee_attack or 0,
        "ranged_attack": user.ranged_attack or 0,
        "magic_power": user.magic_power or 0,
        "physical_defense": user.physical_defense or 0,
        "magic_resistance": user.magic_resistance or 0,
        # Бонуси до шкоди
        "bonus_melee_damage": user.bonus_melee_damage or 0,
        "bonus_ranged_damage": user.bonus_ranged_damage or 0,
        "bonus_magic_damage": user.bonus_magic_damage or 0,
        # Бонуси до захисту
        "bonus_melee_defense": user.bonus_melee_defense or 0,
        "bonus_ranged_defense": user.bonus_ranged_defense or 0,
        "bonus_magic_defense": user.bonus_magic_defense or 0,
    }
