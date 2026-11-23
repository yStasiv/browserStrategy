from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.auth import session_player
from backend import database
from backend.routers.item import ITEM_TYPES
from backend.services import artifact_shop
from backend.services.character_profile import stat_icon_url
from backend.services.hero_attributes import PROFILE_STATS
from backend.services.resource_balances import resource_definitions

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def shop_player(request, db):
    user = session_player(request, db)
    if user is None:
        raise HTTPException(401, "Увійди до гри.")
    return user


def shop_url(my_level, category, *, purchased=False):
    params = {}
    if my_level:
        params["my_level"] = 1
    if category:
        params["category"] = category
    if purchased:
        params["purchased"] = 1
    return "/shop?" + urlencode(params) if params else "/shop"


def render_shop(request, db, user, my_level, category, *, error=None, status=200):
    return templates.TemplateResponse("shop.html", {
        "request": request, "player": user, "offers": artifact_shop.offers(db, user, my_level, category),
        "resource_catalog": resource_definitions(), "item_types": ITEM_TYPES,
        "my_level": my_level, "shop_error": error,
        "category": category, "categories": artifact_shop.SHOP_CATEGORIES, "shop_url": shop_url,
        "bonus_icons": {
            PROFILE_STATS[key][0]: stat_icon_url(key)
            for key in ("attack", "defense", "initiative", "spell_power", "knowledge")
        },
        "purchased": request.query_params.get("purchased") == "1",
    }, status_code=status)


@router.get("/shop")
def shop_page(request: Request, my_level: bool = False, category: str | None = None,
              db: Session = Depends(database.get_db)):
    if category not in artifact_shop.SHOP_CATEGORIES:
        category = None
    return render_shop(request, db, shop_player(request, db), my_level, category)


@router.post("/shop/buy/{shop_item_id}")
def buy_item(shop_item_id: int, request: Request, db: Session = Depends(database.get_db),
             return_to_shop: bool = Form(False), my_level: bool = Form(False), category: str | None = Form(None)):
    if category not in artifact_shop.SHOP_CATEGORIES:
        category = None
    user = shop_player(request, db)
    try:
        artifact_shop.buy(db, user, shop_item_id)
        db.commit()
    except HTTPException as exc:
        if not return_to_shop:
            raise
        db.rollback()
        return render_shop(request, db, user, my_level, category, error=exc.detail, status=exc.status_code)
    if return_to_shop:
        return RedirectResponse(shop_url(my_level, category, purchased=True), status_code=303)
    return {"status": "success"}
