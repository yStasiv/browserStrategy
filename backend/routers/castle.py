from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import database
from ..auth import session_player
from ..engine.battle_service import user_level
from ..services.hero_army import army_options, save_roster
from ..engine.setup import field_rules

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def require_player(request, db):
    player = session_player(request, db)
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    return player


def render_castle(request, player, options, slot_limit, error=None):
    return templates.TemplateResponse("castle.html", {
        "request": request, "player": player, "units": options, "slot_limit": slot_limit,
        "saved": request.query_params.get("saved") == "1" and not error, "error": error,
    }, status_code=422 if error else 200)


@router.get("/castle", response_class=HTMLResponse)
def castle_page(request: Request, db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    return render_castle(request, player, army_options(db, player), field_rules(user_level(player), "pve").max_slots)


@router.post("/castle")
async def save_army(request: Request, db: Session = Depends(database.get_db)):
    form = await request.form()
    player = require_player(request, db)
    try:
        values = {}
        for key, raw in form.multi_items():
            if key in values:
                raise ValueError
            values[key] = int(raw)
        save_roster(db, player, values)
    except (TypeError, ValueError, HTTPException) as error:
        db.rollback()
        if isinstance(error, HTTPException) and error.status_code == 409:
            return RedirectResponse("/battle", status_code=303)
        options = army_options(db, player)
        message = error.detail if isinstance(error, HTTPException) else "Вкажи допустиму кількість для кожного загону."
        return render_castle(request, player, options, field_rules(user_level(player), "pve").max_slots, message)
    return RedirectResponse("/castle?saved=1", status_code=303)
