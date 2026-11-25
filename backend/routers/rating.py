from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import database
from backend.auth import playable_users, session_player
from backend.engine.data import faction_key
from backend.models import User
from backend.services.character_profile import FACTIONS

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/rating", response_class=HTMLResponse)
def rating_page(request: Request, db: Session = Depends(database.get_db)):
    players = playable_users(db).order_by(
        func.coalesce(User.experience, 0).desc(), User.level.desc(), User.id
    ).limit(100).all()
    return templates.TemplateResponse(
        "rating.html",
        {
            "request": request,
            "players": players,
            "player": session_player(request, db),
            "factions": {player.id: FACTIONS.get(faction_key(player.fraction), player.fraction) for player in players},
        },
    )
