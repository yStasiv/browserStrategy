from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_current_user, get_db
from backend.models import User
from backend.engine.battle_service import hunting_options
from backend.services import world

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


class TravelRequest(BaseModel):
    sector: str = Field(min_length=1, max_length=100)


def location_state(db, player):
    journey, now = world.resolve_location(db, player)
    state = world.map_state(db, player, journey, now)
    state["hunts"] = hunting_options(player, journey is not None)
    db.commit()
    return state


@router.get("/map")
def get_map(request: Request, db: Session = Depends(get_db), player: User = Depends(get_current_user)):
    if player is None:
        return RedirectResponse(url="/")
    state = location_state(db, player)
    return templates.TemplateResponse("map.html", {"request": request, "player": player, "world": state})


@router.get("/api/world")
def world_status(db: Session = Depends(get_db), player: User = Depends(get_current_user)):
    if player is None:
        raise HTTPException(401, "Увійдіть до гри.")
    return location_state(db, player)


@router.post("/move-to-sector")
def start_travel(body: TravelRequest, db: Session = Depends(get_db), player: User = Depends(get_current_user)):
    if player is None:
        raise HTTPException(401, "Увійдіть до гри.")
    try:
        journey, now = world.start_travel(db, player, body.sector)
    except HTTPException:
        # A due arrival may have been finalized before the new request was rejected.
        db.commit()
        raise
    state = world.map_state(db, player, journey, now)
    state["hunts"] = hunting_options(player, journey is not None)
    db.commit()
    return state
