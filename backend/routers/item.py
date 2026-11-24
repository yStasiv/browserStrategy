from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import database, models
from backend.auth import session_player
from backend.services.artifact_shop import bonuses as shop_bonuses, costs
from backend.services.character_profile import STAT_LABELS
from backend.services.resource_balances import resource_definitions

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

ITEM_TYPES = {
    "armor": "Броня", "armor:": "Броня", "helmet": "Шолом", "boots": "Чоботи",
    "belt": "Пояс", "back": "Плащ", "shield": "Щит", "jewelry": "Прикраса",
    "one_handed_weapon": "Одноручна зброя", "two_handed_weapon": "Дворучна зброя", "bow": "Лук",
}


@router.get("/art_info")
async def get_item_info(id: int, request: Request, db: Session = Depends(database.get_db)):
    item = db.get(models.Item, id)
    if item is None:
        raise HTTPException(404, "Предмет не знайдено.")
    viewer = session_player(request, db)
    listings = db.query(models.ShopItem).filter_by(item_template_id=item.id).order_by(models.ShopItem.id).all()
    return templates.TemplateResponse("item_info.html", {
        "request": request, "item": item, "player": viewer,
        "item_type": ITEM_TYPES.get(item.item_type, "Інший предмет"),
        "bonuses": shop_bonuses(item.stats) if listings else [
            (STAT_LABELS[key], value) for key, value in (item.stats or {}).items()
            if key in STAT_LABELS and isinstance(value, (int, float)) and value
        ],
        "offers": [{"listing": listing, "prices": [(key, value, False) for key, value in costs(listing).items()]}
                   for listing in listings],
        "resource_catalog": resource_definitions(),
    })
