from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import database, models
from backend.auth import get_current_user
from backend.services.hero_equipment import SLOT_COLUMNS, change_equipment, lock_hero

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/inventory")
async def get_inventory(request: Request, db: Session = Depends(database.get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Отримуємо всі вдягнені предмети
    equipped_items = {}
    if user.equipped_items:
        slots = {
            "helmet_id": "Шолом",
            "armor_id": "Броня",
            "belt_id": "Пояс",
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
            item_id = getattr(user.equipped_items, slot_id)
            if item_id:
                item = db.query(models.Item).filter(models.Item.id == item_id).first()
                if item:
                    equipped_items[slot_name] = item

    # Оновлені бонуси від предметів
    user_data = {
        # Основні характеристики
        "stamina": user.stamina or 0,
        "stamina_bonus": sum(
            item.stats.get("stamina", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "energy": user.energy or 0,
        "energy_bonus": sum(
            item.stats.get("energy", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "agility": user.agility or 0,
        "agility_bonus": sum(
            item.stats.get("agility", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "mind": user.mind or 0,
        "mind_bonus": sum(
            item.stats.get("mind", 0) for item in equipped_items.values() if item.stats
        ),
        # Додаткові характеристики
        "melee_attack": user.melee_attack or 0,
        "melee_attack_bonus": sum(
            item.stats.get("melee_attack", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "ranged_attack": user.ranged_attack or 0,
        "ranged_attack_bonus": sum(
            item.stats.get("ranged_attack", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "magic_power": user.magic_power or 0,
        "magic_power_bonus": sum(
            item.stats.get("magic_power", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "physical_defense": user.physical_defense or 0,
        "physical_defense_bonus": sum(
            item.stats.get("physical_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "magic_resistance": user.magic_resistance or 0,
        "magic_resistance_bonus": sum(
            item.stats.get("magic_resistance", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        # Бонуси до шкоди
        "bonus_melee_damage": user.bonus_melee_damage or 0,
        "bonus_melee_damage_bonus": sum(
            item.stats.get("bonus_melee_damage", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_ranged_damage": user.bonus_ranged_damage or 0,
        "bonus_ranged_damage_bonus": sum(
            item.stats.get("bonus_ranged_damage", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_magic_damage": user.bonus_magic_damage or 0,
        "bonus_magic_damage_bonus": sum(
            item.stats.get("bonus_magic_damage", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        # Бонуси до захисту
        "bonus_melee_defense": user.bonus_melee_defense or 0,
        "bonus_melee_defense_bonus": sum(
            item.stats.get("bonus_melee_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_ranged_defense": user.bonus_ranged_defense or 0,
        "bonus_ranged_defense_bonus": sum(
            item.stats.get("bonus_ranged_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
        "bonus_magic_defense": user.bonus_magic_defense or 0,
        "bonus_magic_defense_bonus": sum(
            item.stats.get("bonus_magic_defense", 0)
            for item in equipped_items.values()
            if item.stats
        ),
    }

    inventory_items = (
        db.query(models.Item)
        .filter(models.Item.owner_id == user.id, models.Item.is_equipped == False)
        .all()
    )

    return templates.TemplateResponse(
        "inventory.html",
        {
            "request": request,
            "user": user_data,
            "inventory_items": inventory_items,
            "equipped_items": equipped_items,
            "max_items": 30,
        },
    )


@router.post("/inventory/equip/{item_id}")
async def equip_item(item_id: int, request: Request, db: Session = Depends(database.get_db), slot: str = None):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Увійди до гри.")
    aliases = {column: key for key, column in SLOT_COLUMNS.items()}
    change_equipment(db, user, slot=aliases.get(slot, slot), item_id=item_id)
    db.commit()
    return {"status": "success"}


@router.post("/inventory/unequip/{item_id}")
async def unequip_item(item_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Увійди до гри.")
    change_equipment(db, user, item_id=item_id, remove=True)
    db.commit()
    return {"status": "success"}


@router.post("/inventory/destroy/{item_id}")
async def destroy_item(
    item_id: int, request: Request, db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    lock_hero(db, user)
    item = (
        db.query(models.Item)
        .filter(models.Item.id == item_id, models.Item.owner_id == user.id)
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    change_equipment(db, user, item_id=item_id, remove=True)

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
