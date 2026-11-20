from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import database, models
from ..auth import session_player
from ..engine.battle_models import ArmySlot
from ..engine.battle_service import get_active_battle_id, user_level
from ..engine.data import DEFAULT_ARMY, UNITS
from ..engine.setup import field_rules

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def require_player(request, db):
    player = session_player(request, db)
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    return player


def army_options(db, player):
    slots = db.scalars(select(ArmySlot).where(ArmySlot.user_id == player.id).order_by(ArmySlot.slot)).all()
    counts = {}
    for slot in slots:
        counts[slot.unit_key] = counts.get(slot.unit_key, 0) + slot.count
    if not slots:
        counts = dict(DEFAULT_ARMY)
    limits = {
        unit.key: unit.recruitment.max_count
        for unit in UNITS.values()
        if unit.recruitment and unit.recruitment.min_level <= user_level(player)
        and (not unit.recruitment.factions or player.fraction in unit.recruitment.factions)
    }
    for key, count in counts.items():
        limits[key] = max(limits.get(key, 0), count)
    return [
        {"key": key, "name": UNITS[key].name, "quantity": counts.get(key, 0), "limit": limit}
        for key, limit in limits.items() if key in UNITS
    ]


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
    db.execute(update(models.User).where(models.User.id == player.id).values(map_sector=models.User.map_sector))
    if get_active_battle_id(db, player.id) is not None:
        return RedirectResponse("/battle", status_code=303)
    options = army_options(db, player)
    slot_limit = field_rules(user_level(player), "pve").max_slots
    values = {}
    error = "Вкажи допустиму кількість для кожного загону."
    try:
        for key, raw in form.multi_items():
            if key in values:
                raise ValueError
            values[key] = int(raw)
        limits = {unit["key"]: unit["limit"] for unit in options}
        if values.keys() != limits.keys() or any(not 0 <= values[key] <= cap for key, cap in limits.items()):
            raise ValueError
    except (TypeError, ValueError):
        return render_castle(request, player, options, slot_limit, error)

    army = [(unit["key"], values[unit["key"]]) for unit in options if values[unit["key"]]]
    if not 1 <= len(army) <= slot_limit:
        for unit in options:
            unit["quantity"] = values[unit["key"]]
        return render_castle(request, player, options, slot_limit, f"Обери від 1 до {slot_limit} загонів.")

    existing = db.scalars(select(ArmySlot).where(ArmySlot.user_id == player.id)).all()
    by_slot = {entry.slot: entry for entry in existing}
    for index, (key, count) in enumerate(army):
        entry = by_slot.pop(index, None)
        if entry is None:
            db.add(ArmySlot(user_id=player.id, slot=index, unit_key=key, count=count))
        else:
            entry.unit_key, entry.count = key, count
    for entry in by_slot.values():
        db.delete(entry)
    db.commit()
    return RedirectResponse("/castle?saved=1", status_code=303)
