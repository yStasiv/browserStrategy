from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import database, models
from ..engine import battle_service
from ..services import admin_stats, enterprises, world
from ..world_models import SectorConnection, WorldSector

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def world_admin(user: models.User = Depends(database.get_current_user)):
    if not user or not user.is_admin:
        raise HTTPException(403, "Потрібні права адміністратора.")
    return user


ENTERPRISE_TYPES = {"mine": "Шахта", "processing": "Переробка", "factory": "Виробництво"}


def enterprise_fields(
    name: str = Form(..., min_length=1, max_length=120),
    sector: str = Form(...),
    resource_type: str = Form(...),
    area: int = Form(100, ge=1, le=999),
    storage_multiplier: int = Form(40, ge=1, le=999),
    production_type: str = Form("mine"),
    salary: int = Form(..., ge=1, le=2_147_483_647),
    item_price: int = Form(..., ge=1, le=2_147_483_647),
    max_workers: int | None = Form(None, ge=1, le=2_147_483_647),
    max_storage: int | None = Form(None, ge=1, le=2_147_483_647),
):
    return dict(name=name.strip(), sector=sector, resource_type=resource_type, area=area,
                storage_multiplier=storage_multiplier, production_type=production_type,
                salary=salary, item_price=item_price, max_workers=max_workers or area * 3,
                max_storage=max_storage or area * storage_multiplier)


def render_enterprises(request, db, user, *, error=None, status=200):
    return templates.TemplateResponse("admin_enterprises.html", {
        "request": request, "player": user,
        "enterprises": db.query(models.Enterprise).order_by(models.Enterprise.sector, models.Enterprise.name).all(),
        "sectors": world.sectors(db), "resources": enterprises.resource_names(),
        "enterprise_types": ENTERPRISE_TYPES, "enterprise_error": error,
    }, status_code=status)


@router.get("/admin/enterprises")
def admin_enterprises(request: Request, db: Session = Depends(database.get_db),
                      user: models.User = Depends(world_admin)):
    return render_enterprises(request, db, user)


@router.post("/admin/enterprises/add")
@router.post("/admin/enterprises/edit/{enterprise_id}")
def save_enterprise(
    request: Request, enterprise_id: int | None = None, fields: dict = Depends(enterprise_fields),
    db: Session = Depends(database.get_db), user: models.User = Depends(world_admin),
):
    try:
        if not fields["name"]:
            raise HTTPException(422, "Вкажи назву підприємства.")
        if db.get(WorldSector, fields["sector"]) is None:
            raise HTTPException(422, "Обери наявний сектор.")
        if fields["resource_type"] not in enterprises.resource_names() or fields["production_type"] not in ENTERPRISE_TYPES:
            raise HTTPException(422, "Обери наявний ресурс і тип підприємства.")
        if enterprise_id is None:
            db.add(models.Enterprise(**fields))
        else:
            site = enterprises.lock_enterprise(db, enterprise_id)
            if fields["max_storage"] < site.resource_stored or fields["max_workers"] < site.workers_count:
                raise HTTPException(409, "Нові ліміти мають вміщати поточні запаси й працівників.")
            if site.workers_count and any(fields[key] != getattr(site, key)
                                          for key in ("sector", "resource_type", "production_type")):
                raise HTTPException(409, "Дочекайся завершення змін, перш ніж змінювати сектор, ресурс або тип.")
            if site.resource_stored and fields["resource_type"] != site.resource_type:
                raise HTTPException(409, "Ресурс можна змінити після спорожнення складу.")
            for key, value in fields.items():
                setattr(site, key, value)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        return render_enterprises(request, db, user, error=exc.detail, status=exc.status_code)
    return RedirectResponse("/admin/enterprises", status_code=303)


@router.post("/admin/enterprises/delete/{enterprise_id}")
async def delete_enterprise(
    enterprise_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(world_admin),
):
    if db.get(models.Enterprise, enterprise_id) is not None:
        site = enterprises.lock_enterprise(db, enterprise_id)
        if db.query(models.User.id).filter(models.User.workplace == f"enterprise_{enterprise_id}").first():
            db.rollback()
            return render_enterprises(request, db, user, error="Дочекайся завершення робочих змін.", status=409)
        db.delete(site)
        db.commit()

    return RedirectResponse(url="/admin/enterprises", status_code=303)




def save_world(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Запис уже існує або його було змінено. Онови сторінку.") from exc
    return RedirectResponse("/admin/world", status_code=303)


@router.get("/admin/world")
def admin_world(request: Request, db: Session = Depends(database.get_db), user: models.User = Depends(world_admin)):
    return templates.TemplateResponse("admin/world.html", {
        "request": request, "player": user, "sectors": world.sectors(db),
        "connections": db.query(SectorConnection).order_by(SectorConnection.origin, SectorConnection.destination).all(),
    })


@router.post("/admin/world/sectors")
def add_sector(
    key: str = Form(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
    name: str = Form(..., min_length=1, max_length=100),
    unlocked: bool = Form(False),
    sort_order: int = Form(0, ge=0, le=2_147_483_647),
    map_x: int | None = Form(None, ge=0, le=100),
    map_y: int | None = Form(None, ge=0, le=100),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(world_admin),
):
    if not name.strip():
        raise HTTPException(422, "Вкажи назву сектора.")
    if (map_x is None) != (map_y is None):
        raise HTTPException(422, "Вкажи обидві координати або залиш обидві порожніми.")
    db.add(WorldSector(key=key, name=name.strip(), unlocked=unlocked, sort_order=sort_order, map_x=map_x, map_y=map_y))
    return save_world(db)


@router.post("/admin/world/sectors/{key}/unlock")
def unlock_sector(key: str, db: Session = Depends(database.get_db), user: models.User = Depends(world_admin)):
    world.unlock_sector(db, key)
    return save_world(db)


@router.post("/admin/world/connections")
def save_connection(
    origin: str = Form(...),
    destination: str = Form(...),
    duration_seconds: int = Form(..., gt=0, le=2_147_483_647),
    bidirectional: bool = Form(True),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(world_admin),
):
    world.set_connection(db, origin, destination, duration_seconds, bidirectional)
    return save_world(db)


@router.get("/admin/stats")
def stats_page(request: Request, user: models.User = Depends(world_admin)):
    return templates.TemplateResponse("admin/stats.html", {"request": request, "player": user},
                                      headers={"Cache-Control": "no-store"})


@router.get("/admin/api/stats")
def stats_data(response: Response, period: Literal["24h", "7d", "30d", "all"] = "7d",
               limit: int = Query(20, ge=1, le=100), db: Session = Depends(database.get_db),
               user: models.User = Depends(world_admin)):
    response.headers["Cache-Control"] = "no-store"
    return admin_stats.dashboard(db, period, limit)


@router.get("/admin/api/stats/replay/{battle_id}")
def stats_replay(battle_id: int, response: Response, db: Session = Depends(database.get_db),
                 user: models.User = Depends(world_admin)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return battle_service.battle_events(db, user, battle_id, finished_only=True, spectate=True)
    except battle_service.BattleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
