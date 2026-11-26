from math import ceil

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import database
from ..auth import session_player
from ..engine.battle_service import get_active_battle_id, user_level
from ..engine.data import UNITS, faction_key
from ..engine.hero import make_hero
from ..engine.summoning import SPELLS, hp_pool, max_energy, school_spells
from ..guild_models import ActivityGuildProgress
from ..models import Item, RepairJob
from ..services import activity_guilds, castle_buildings, forge_repairs
from ..services.hero_army import army_options, recruitment_cards, save_roster
from ..services.world import require_presence, utc_now
from ..engine.setup import field_rules

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

WORKSHOPS = activity_guilds.WORKSHOPS
REPAIR_WORKSHOPS = {item_type: key for key, (_, types) in WORKSHOPS.items() for item_type in types}


def require_player(request, db):
    player = session_player(request, db)
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    return player


def render_castle(request, db, player, error=None, building_error=None):
    entries, resource_catalog = castle_buildings.catalog()
    built = castle_buildings.built_ids(db, player, entries)
    faction = faction_key(player.fraction)
    school_level = castle_buildings.school_level(built)
    spells = school_spells(school_level, is_elf=faction == "elves")
    recruits_by_building = {}
    for unit in UNITS.values():
        recruitment = unit.recruitment
        if recruitment and (not recruitment.factions or faction in map(faction_key, recruitment.factions)):
            recruits_by_building.setdefault(recruitment.building, []).append(unit)
    spells_by_building = {
        key: [spell for spell in spells if faction == "elves" and spell["required_school_level"] == level]
        for key, level in castle_buildings.MAGIC_SCHOOL_LEVELS.items()
    }
    forms_by_line = {(unit.line, unit.form): unit for unit in UNITS.values() if unit.line and unit.form}
    previous_forms = {
        unit.key: previous
        for (line, form), unit in forms_by_line.items()
        if (previous := forms_by_line.get((line, form - 1))) is not None
    }
    buildings = [
        building for building in entries.values()
        if castle_buildings.available_to_faction(building, player)
    ]
    buildings.sort(key=lambda building: building.min_level)
    unaffordable = castle_buildings.unaffordable_buildings(
        db, player, [building for building in buildings if building.id not in built],
    )
    army = army_options(db, player, built)
    build_icon = (
        "/static/images/buildings/build.png" if castle_buildings.BUILD_ICON_FILE.is_file()
        else "/static/images/guild_icons/workshop_weapons.png"
    )
    return templates.TemplateResponse("castle.html", {
        "request": request, "player": player, "faction": faction,
        "units": recruitment_cards(army),
        "retained_squads": sum(not unit["recruitable"] and unit["quantity"] > 0 for unit in army),
        "slot_limit": field_rules(user_level(player), "pve").max_slots,
        "buildings": buildings, "unaffordable": unaffordable,
        "built": built, "resource_catalog": resource_catalog, "build_icon": build_icon,
        "forge_built": castle_buildings.FORGE in built,
        "magic_school_built": castle_buildings.MAGIC_SCHOOL in built,
        "school_level": school_level, "spells": spells,
        "recruits_by_building": recruits_by_building, "spells_by_building": spells_by_building,
        "previous_forms": previous_forms,
        "building_names": {key: building.name for key, building in entries.items()},
        "building_error": building_error,
        "saved": request.query_params.get("saved") == "1" and not error, "error": error,
    }, status_code=building_error.status_code if building_error else (422 if error else 200))


@router.get("/castle", response_class=HTMLResponse)
def castle_page(request: Request, db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    return render_castle(request, db, player)


def magic_school_data(db, player):
    entries, _ = castle_buildings.catalog()
    level = castle_buildings.school_level(castle_buildings.built_ids(db, player, entries))
    hero = make_hero(db, player, 0, user_level(player))
    return {
        "school_level": level, "spell_power": hero.spell_power, "knowledge": hero.knowledge,
        "summon_hp": hp_pool(hero.spell_power), "max_energy": max_energy(hero.knowledge),
        "spells": school_spells(level, is_elf=hero.faction == "elves"),
    }


@router.get("/api/castle/magic/spells")
def castle_spells(request: Request, db: Session = Depends(database.get_db)):
    return magic_school_data(db, require_player(request, db))


@router.get("/castle/magic/spell/{spell_id}", response_class=HTMLResponse)
def spell_info(spell_id: str, request: Request, db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    if spell_id not in SPELLS:
        raise HTTPException(404, "Закляття не знайдено.")
    magic = magic_school_data(db, player)
    spell = next(row for row in magic["spells"] if row["id"] == spell_id)
    return templates.TemplateResponse("spell_info.html", {
        "request": request, "player": player, "spell": spell, "magic": magic,
        "unit": UNITS[spell["summon_unit_id"]],
    })


@router.get("/unit_info", response_class=HTMLResponse)
def unit_info(request: Request, key: str):
    unit = UNITS.get(key)
    if unit is None:
        raise HTTPException(404, "Юніта не знайдено.")
    return templates.TemplateResponse("unit_info.html", {"request": request, "unit": unit})


@router.post("/castle/build")
def construct_building(request: Request, building_id: str = Form(...), db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    try:
        require_presence(db, player, "Castle")
        if get_active_battle_id(db, player.id) is not None:
            return RedirectResponse("/battle", status_code=303)
        castle_buildings.build(db, player, building_id)
    except HTTPException as error:
        db.rollback()
        return render_castle(request, db, player, building_error=error)
    db.commit()
    return RedirectResponse("/castle?section=building", status_code=303)


def require_forge(db, player):
    require_presence(db, player, "Castle")
    entries, _ = castle_buildings.catalog()
    if castle_buildings.FORGE not in castle_buildings.built_ids(db, player, entries):
        raise HTTPException(403, "Спочатку побудуй Кузню.")


def repairable_items(player):
    return select(Item).where(
        Item.owner_id == player.id,
        Item.item_type.in_(REPAIR_WORKSHOPS),
        Item.durability >= 0,
        Item.max_durability > 1,
        Item.durability * 2 <= Item.max_durability,
    )


def metalworking_progress(db, player):
    return activity_guilds.progress(db, player.id, activity_guilds.METALWORKERS)


@router.get("/castle/metalworking", response_class=HTMLResponse)
def metalworking_page(request: Request, db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    require_forge(db, player)
    db.commit()
    progress = metalworking_progress(db, player)
    unlocked = activity_guilds.workshop_progress(db, player.id)
    items = db.scalars(repairable_items(player).order_by(Item.name, Item.id)).all()
    prices = forge_repairs.repair_prices()
    quotes = {}
    job = db.get(RepairJob, player.id)
    job_item = db.get(Item, job.item_id) if job else None
    remaining = max(0, ceil((job.ready_at - utc_now()).total_seconds())) if job else 0
    show_result = bool(job_item and job_item.owner_id == player.id and not remaining
                       and request.query_params.get("result") == job.token)
    for item in items:
        price = prices.get((item.name, item.item_type))
        specialization = unlocked.get(REPAIR_WORKSHOPS[item.item_type])
        if price is not None and specialization:
            quotes[item.id] = forge_repairs.preview(item, specialization["level"], price)
    workshops = [
        (key, name, unlocked.get(key), [item for item in items if item.item_type in types and (job is None or item.id != job.item_id)])
        for key, (name, types) in WORKSHOPS.items()
    ]
    return templates.TemplateResponse("metalworking.html", {
        "request": request, "player": player, "progress": progress,
        "workshops": workshops, "workshop_icons": activity_guilds.WORKSHOP_ICONS,
        "unlocked_count": len(unlocked),
        "repair_percent": activity_guilds.repair_percent,
        "repair_quotes": quotes, "job": job, "job_item": job_item, "remaining": remaining,
        "show_result": show_result,
        "repaired_durability": forge_repairs.repaired_durability(job, job_item)
        if show_result and job.succeeded else None,
    })


@router.post("/castle/metalworking/unlock")
def unlock_workshop(
    request: Request, workshop: str = Form(...), db: Session = Depends(database.get_db),
):
    player = require_player(request, db)
    require_forge(db, player)
    if get_active_battle_id(db, player.id) is not None:
        return RedirectResponse("/battle", status_code=303)
    if workshop not in WORKSHOPS:
        raise HTTPException(404, "Майстерню не знайдено.")

    college = metalworking_progress(db, player)
    unlocked = activity_guilds.workshop_progress(db, player.id)
    if workshop not in unlocked:
        if len(unlocked) >= college["level"]:
            raise HTTPException(409, "Спочатку підвищ рівень Колегії, щоб відкрити ще одну майстерню.")
        if workshop == "enchanting" and college["level"] < activity_guilds.MAX_COLLEGE_LEVEL:
            raise HTTPException(409, "Зачарувальня доступна з четвертого рівня Колегії.")
        db.add(ActivityGuildProgress(player_id=player.id, guild=activity_guilds.workshop_key(workshop), points=0))
    db.commit()
    return RedirectResponse(f"/castle/metalworking#{workshop}", status_code=303)


@router.post("/castle/metalworking/repair")
def repair_artifact(
    request: Request, item_id: int = Form(..., gt=0), durability: int = Form(..., ge=0),
    confirmed: bool = Form(False),
    db: Session = Depends(database.get_db),
):
    player = require_player(request, db)
    require_forge(db, player)
    if get_active_battle_id(db, player.id) is not None:
        return RedirectResponse("/battle", status_code=303)
    item = db.scalar(repairable_items(player).where(Item.id == item_id))
    if item is None or item.durability != durability:
        raise HTTPException(409, "Предмет уже відремонтовано або він недоступний для ремонту.")

    workshop = REPAIR_WORKSHOPS[item.item_type]
    specialization = activity_guilds.workshop_progress(db, player.id).get(workshop)
    if specialization is None:
        raise HTTPException(403, "Спочатку відкрий відповідну майстерню.")

    gold = forge_repairs.repair_prices().get((item.name, item.item_type))
    if gold is None:
        raise HTTPException(409, "Для артефакту немає ціни ремонту.")
    forge_repairs.start(db, player, item, workshop, specialization["level"], gold, utc_now(), confirmed)
    db.commit()
    return RedirectResponse(f"/castle/metalworking#{workshop}", status_code=303)


@router.get("/castle/metalworking/repair/status")
def repair_status(request: Request, db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    require_forge(db, player)
    job = db.get(RepairJob, player.id)
    if job is None:
        return {"status": "idle"}
    remaining = max(0, ceil((job.ready_at - utc_now()).total_seconds()))
    return {"status": "running" if remaining else "ready", "remaining_seconds": remaining}


@router.post("/castle/metalworking/repair/claim")
def collect_repair(request: Request, token: str = Form(...), db: Session = Depends(database.get_db)):
    player = require_player(request, db)
    require_forge(db, player)
    if get_active_battle_id(db, player.id) is not None:
        return RedirectResponse("/battle", status_code=303)
    _, workshop = forge_repairs.claim(db, player, token, utc_now())
    db.commit()
    return RedirectResponse(f"/castle/metalworking#{workshop}", status_code=303)


@router.post("/castle")
async def save_army(request: Request, db: Session = Depends(database.get_db)):
    form = await request.form()
    player = require_player(request, db)
    try:
        values, forms = {}, {}
        for key, raw in form.multi_items():
            if key.startswith("form:"):
                line = key.removeprefix("form:")
                if line in forms:
                    raise ValueError
                forms[line] = str(raw)
            elif key in values:
                raise ValueError
            else:
                values[key] = int(raw)
        save_roster(db, player, values, forms)
    except (TypeError, ValueError, HTTPException) as error:
        db.rollback()
        if isinstance(error, HTTPException) and error.status_code == 409:
            return RedirectResponse("/battle", status_code=303)
        message = error.detail if isinstance(error, HTTPException) else "Вкажи допустиму кількість для кожного загону."
        return render_castle(request, db, player, error=message)
    return RedirectResponse("/castle?saved=1", status_code=303)
