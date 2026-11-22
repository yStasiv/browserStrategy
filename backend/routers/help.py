from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.auth import session_player
from backend import database
from backend.engine.data import FACTION_ROSTERS, SUMMONING, UNITS

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/creatures/catalog")
def creature_catalog():
    return {
        "factions": FACTION_ROSTERS,
        "summoning": SUMMONING,
        "units": UNITS,
    }


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request, db: Session = Depends(database.get_db)):
    # Отримуємо користувача з сесії
    user_session_id = request.cookies.get("session_id")
    user = None
    if user_session_id:
        user = session_player(request, db)

    return templates.TemplateResponse("help.html", {
        "request": request, "user": user, "creatures": UNITS.values(),
    })
