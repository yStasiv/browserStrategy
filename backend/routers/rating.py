from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend import database, models
from backend.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

@router.get("/rating", response_class=HTMLResponse)
async def rating_page(request: Request, db: Session = Depends(database.get_db)):
    # Отримуємо поточного користувача
    current_user = await get_current_user(request, db)
    
    # Отримуємо всіх гравців з їх рейтингами
    players = db.query(models.User).join(models.PlayerRating).all()
    
    # Сортуємо гравців за рейтингом (за замовчуванням)
    players.sort(key=lambda x: x.rating.rating, reverse=True)
    
    return templates.TemplateResponse(
        "rating.html",
        {
            "request": request,
            "players": players,
            "current_user": current_user
        }
    ) 