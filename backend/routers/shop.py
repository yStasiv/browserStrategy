from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import database, models

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/shop")
async def shop_page(request: Request, db: Session = Depends(database.get_db)):
    player_session_id = request.cookies.get("session_id")
    if not player_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    player = (
        db.query(models.User).filter(models.User.session_id == player_session_id).first()
    )
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Отримуємо доступні товари
    shop_items = (
        db.query(models.ShopItem)
        .filter(models.ShopItem.level_required <= player.level)
        .all()
    )

    return templates.TemplateResponse(
        "shop.html", {"request": request, "player": player, "shop_items": shop_items}
    )


@router.post("/shop/buy/{shop_item_id}")
async def buy_item(
    shop_item_id: int, request: Request, db: Session = Depends(database.get_db)
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = (
        db.query(models.User).filter(models.User.session_id == user_session_id).first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    shop_item = (
        db.query(models.ShopItem).filter(models.ShopItem.id == shop_item_id).first()
    )

    if not shop_item:
        raise HTTPException(status_code=404, detail="Item not found in shop")

    # Перевірка рівня
    if user.level < shop_item.level_required:
        raise HTTPException(
            status_code=400, detail=f"Required level: {shop_item.level_required}"
        )

    # Перевірка наявності
    if shop_item.quantity == 0:
        raise HTTPException(status_code=400, detail="Item out of stock")

    # Перевірка золота
    if user.gold < shop_item.price:
        raise HTTPException(status_code=400, detail="Not enough gold")

    # Перевірка місця в інвентарі
    inventory_count = (
        db.query(models.Item).filter(models.Item.owner_id == user.id).count()
    )

    if inventory_count >= 30:
        raise HTTPException(status_code=400, detail="Inventory is full")

    # Створюємо копію предмета для користувача
    new_item = models.Item(
        name=shop_item.item_template.name,
        description=shop_item.item_template.description,
        item_type=shop_item.item_template.item_type,
        image_url=shop_item.item_template.image_url,
        stats=shop_item.item_template.stats,
        owner_id=user.id,
    )

    # Знімаємо золото
    user.gold -= shop_item.price

    # Оновлюємо кількість, якщо вона обмежена
    if shop_item.quantity > 0:
        shop_item.quantity -= 1

    db.add(new_item)
    db.commit()

    return {"status": "success"}
