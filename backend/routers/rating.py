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
    player = await get_current_user(request, db)
    
    # Отримуємо всіх гравців
    players = db.query(models.User).all()
    
    # Для кожного гравця перевіряємо наявність рейтингу
    for player in players:
        player_rating = db.query(models.PlayerRating).filter(
            models.PlayerRating.user_id == player.id
        ).first()
        
        if not player_rating:
            # Якщо рейтингу немає, створюємо новий
            player_rating = models.PlayerRating(user_id=player.id)
            db.add(player_rating)
            db.commit()
            db.refresh(player_rating)
        
        # Додаємо рейтинг до об'єкту гравця
        player.rating = player_rating
    
    # Сортуємо гравців за рейтингом
    players.sort(key=lambda x: x.rating.rating, reverse=True)
    
    return templates.TemplateResponse(
        "rating.html",
        {
            "request": request,
            "players": players,
            "player": player
        }
    ) 