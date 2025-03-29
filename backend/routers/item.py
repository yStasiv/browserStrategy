from typing import List

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import database, models

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/art_info")
async def get_item_info(id: int, request: Request, db: Session = Depends(database.get_db)):
    item = db.query(models.Item).filter(models.Item.id == id).first()
    # if int(item.durability) > 0:  # продебажить чого вертається None
    #     return 0
    if item.item_type == 'armor:':
        item.item_type = 'Броня'

    return templates.TemplateResponse(
        "item_info.html",
        {
            "request": request,
            "item": item,
        },
    )
