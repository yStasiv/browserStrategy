from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend import database, models
from backend.auth import session_player
from backend.engine.battle_service import get_active_battle_id
from backend.engine.data import faction_key
from backend.routers.item import ITEM_TYPES
from backend.services.artifact_shop import bonuses
from backend.services.character_profile import equipment_model_url, equipment_state
from backend.services.hero_attributes import PROFILE_STATS
from backend.services.hero_equipment import (
    INVENTORY_LIMIT, MODIFIED_STATS, SLOT_COLUMNS, change_equipment, equipment_ids, lock_hero,
    require_item_not_under_repair,
)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def inventory_player(request, db):
    user = session_player(request, db)
    if user is None:
        raise HTTPException(401, "Увійди до гри.")
    return user


def render_inventory(request, db, player, *, error=None, status=200):
    attributes, equipment, owned = equipment_state(db, player)
    equipped = {slot["item"]["id"] for slot in equipment.values() if slot["item"]}
    inventory = [item for item in owned if item.id not in equipped]
    profile = {
        "attributes": attributes,
        "equipment": equipment,
        "equipment_model_url": equipment_model_url(faction_key(player.fraction), player.gender or "male"),
    }
    return templates.TemplateResponse("inventory.html", {
        "request": request, "player": player, "profile": profile,
        "inventory": inventory, "owned_count": len(owned), "max_items": INVENTORY_LIMIT, "item_types": ITEM_TYPES,
        "artifact_bonuses": {item.id: bonuses(item.stats) for item in owned},
        "inventory_error": error,
    }, status_code=status)


@router.get("/inventory")
def get_inventory(request: Request, db: Session = Depends(database.get_db)):
    return render_inventory(request, db, inventory_player(request, db))


@router.post("/inventory/{action}/{item_id}")
def update_inventory(
    action: Literal["equip", "unequip", "destroy"], item_id: int, request: Request,
    db: Session = Depends(database.get_db), slot: str | None = None,
    selected_slot: str | None = Form(None), return_to_inventory: bool = Form(False),
    replace: bool = Form(False),
):
    user = inventory_player(request, db)
    try:
        lock_hero(db, user)
        if get_active_battle_id(db, user.id) is not None:
            raise HTTPException(409, "Під час бою спорядження змінити неможливо.")
        item = db.scalar(select(models.Item).where(models.Item.id == item_id, models.Item.owner_id == user.id))
        if item is None:
            raise HTTPException(404, "Предмет не знайдено.")
        require_item_not_under_repair(db, user, item.id)
        if action == "equip":
            slot = selected_slot if selected_slot is not None else slot
            aliases = {column: key for key, column in SLOT_COLUMNS.items()}
            change_equipment(db, user, slot=aliases.get(slot, slot), item_id=item.id, replace=replace)
        else:
            worn = item.id in equipment_ids(user.equipped_items).values()
            if action == "unequip" and not worn:
                raise HTTPException(409, "Цей артефакт не вдягнено.")
            if worn:
                change_equipment(db, user, item_id=item.id, remove=True)
            if action == "destroy":
                db.execute(update(models.RewardTransaction).where(models.RewardTransaction.item_id == item.id)
                           .values(item_id=None))
                db.delete(item)
        db.commit()
    except HTTPException as exc:
        if not return_to_inventory:
            raise
        db.rollback()
        message = exc.detail["message"] if isinstance(exc.detail, dict) else exc.detail
        return render_inventory(request, db, user, error=message, status=exc.status_code)
    if return_to_inventory:
        return RedirectResponse("/inventory", status_code=303)
    return {"status": "success"}


@router.get("/inventory/stats")
def get_stats(request: Request, db: Session = Depends(database.get_db)):
    player = inventory_player(request, db)
    attributes, _, _ = equipment_state(db, player)
    totals = {column: getattr(player, column) or 0 for column in MODIFIED_STATS}
    totals.update({column: attributes[key]["total"] for key, (_, column, _) in PROFILE_STATS.items()})
    return totals
