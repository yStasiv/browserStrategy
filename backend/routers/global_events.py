from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend import database
from backend.models import Enterprise, EventReward, GlobalEvent, GlobalEventAudit, ShopItem, User
from backend.routers.admin import world_admin
from backend.services import global_events as events, news, world
from backend.services.resource_balances import resource_definitions

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")
DB = Depends(database.get_db)
ADMIN = Depends(world_admin)


def require_player(player: User = Depends(database.get_current_user)):
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    return player


PLAYER = Depends(require_player)


class Confirmation(BaseModel):
    confirmed: bool


class Contribution(BaseModel):
    resource: str
    quantity: int = Field(strict=True, gt=0, le=2_147_483_647)
    operation_id: UUID


class IssueRequest(Confirmation):
    plan: events.RewardPlan | None = None


def confirm(body):
    if not body.confirmed:
        raise HTTPException(422, "Підтвердь операцію.")


def current(db):
    events.finish_due(db)
    db.commit()


def event_summary(db, event):
    projects = events.projects(db, event.id)
    return {
        "id": event.id, "title": event.title, "summary": event.summary, "image_url": event.image_url,
        "status": event.status, "sector": event.sector, "started_at": events.timestamp(event.started_at),
        "completed_at": events.timestamp(event.completed_at), "project_count": len(projects),
        "started_display": news.display_date(event.started_at), "completed_display": news.display_date(event.completed_at),
        "operational_count": sum(build.operational_since is not None for build in projects),
    }


def event_list(db, active=False):
    query = select(GlobalEvent).where(GlobalEvent.status.in_(
        ["ACTIVE"] if active else ["ACTIVE", "COMPLETED", "REWARDED", "PAUSED"]))
    return [event_summary(db, event) | {
        key: value for key, value in events.statistics(db, event.id).items() if key not in {"ranking", "value"}
    } for event in db.scalars(query.order_by(GlobalEvent.id.desc()))]


@router.get("/events")
def events_page(request: Request, db: Session = DB, player: User = PLAYER):
    current(db)
    return templates.TemplateResponse("events.html", {"request": request, "player": player,
        "entries": event_list(db), "resource_names": resource_definitions()})


@router.get("/events/active")
def active_events(db: Session = DB, player: User = PLAYER):
    current(db)
    return event_list(db, active=True)


@router.get("/events/{event_id}")
def event_page(event_id: int, request: Request, db: Session = DB, player: User = PLAYER):
    current(db)
    event = events.event_or_404(db, event_id)
    stats = event_stats(db, event, player)
    return templates.TemplateResponse("events.html", {"request": request, "player": player, "event": event,
        "stats": stats, "entries": [event_summary(db, event)], "resource_names": resource_definitions(),
        "body": events.notification_text(event)})


def event_stats(db, event, player, enterprise_id=None, resource=None, page=None):
    projects = events.projects(db, event.id)
    if enterprise_id is not None and not any(build.enterprise_id == enterprise_id for build in projects):
        raise HTTPException(404, "Підприємство не належить події.")
    if resource is not None and resource not in resource_definitions():
        raise HTTPException(422, "Ресурс не знайдено.")
    stats = events.statistics(db, event.id, enterprise_id=enterprise_id, resource=resource)
    rows = [public_contribution(row) for row in stats.pop("ranking")]
    stats.pop("value")
    pagination = {} if page is None else {"page": page, "pages": max(1, (len(rows) + 24) // 25)}
    return {**stats, **pagination, "rankings": rows if page is None else rows[(page - 1) * 25:page * 25],
        "personal": next((row for row in rows if row["player_id"] == player.id), None),
        "enterprises": [{"id": build.enterprise_id, "name": db.get(Enterprise, build.enterprise_id).name,
                         "stage": ("Будівництво призупинено" if event.status == "PAUSED" and not build.operational_since
                                   else events.STAGES[events.stage(build, world.utc_now())])}
                        for build in projects if build.enterprise_id is not None]}


@router.get("/events/{event_id}/statistics")
def statistics(event_id: int, enterprise_id: int | None = None, resource: str | None = None,
               page: int = Query(1, ge=1), db: Session = DB, player: User = PLAYER):
    current(db)
    return event_stats(db, events.event_or_404(db, event_id), player, enterprise_id, resource, page)


def public_contribution(row):
    return {key: value for key, value in row.items() if key not in {"value", "percent"}}


@router.get("/events/{event_id}/contributions/me")
def personal(event_id: int, db: Session = DB, player: User = PLAYER):
    current(db)
    events.event_or_404(db, event_id)
    return next((public_contribution(row) for row in events.rankings(db, event_id)
                 if row["player_id"] == player.id), None)


@router.get("/enterprise/{enterprise_id}/construction")
def construction(enterprise_id: int, db: Session = DB, player: User = PLAYER):
    current(db)
    site = db.get(Enterprise, enterprise_id)
    build = events.for_site(db, enterprise_id)
    if not site or not build:
        raise HTTPException(404, "Будівництво не знайдено.")
    world.require_presence(db, player, site.sector, "enterprises")
    state = events.construction_state(db, build, player, world.utc_now())
    db.commit()
    return state


@router.post("/enterprise/{enterprise_id}/construction/contribute")
def contribute(enterprise_id: int, body: Contribution, db: Session = DB, player: User = PLAYER):
    try:
        build = events.contribute(db, player, enterprise_id, body.resource, body.quantity, str(body.operation_id))
    except HTTPException as error:
        if error.status_code != 409:
            raise
        db.rollback()
        site = db.get(Enterprise, enterprise_id)
        build = events.for_site(db, enterprise_id)
        if site is None or build is None:
            raise error
        try:
            world.require_presence(db, player, site.sector, "enterprises")
        except HTTPException:
            raise error
        state = events.construction_state(db, build, player, world.utc_now())
        db.commit()
        return JSONResponse({"detail": error.detail, "construction": state}, status_code=409)
    state = events.construction_state(db, build, player, world.utc_now())
    db.commit()
    return state


@router.get("/admin/events")
@router.get("/admin/events/{event_id}")
@router.get("/admin/events/new")
def admin_events(request: Request, event_id: int | None = None, db: Session = DB, admin: User = ADMIN):
    current(db)
    event = events.event_or_404(db, event_id, admin=True) if event_id else None
    creating = request.url.path == "/admin/events/new"
    catalog = {key: {**definition, "images": events.stage_images(key)}
               for key, definition in events.catalog()["types"].items()}
    builds = events.projects(db, event.id) if event else []
    build_names = dict(db.execute(select(Enterprise.id, Enterprise.name).where(
        Enterprise.id.in_([build.enterprise_id for build in builds if build.enterprise_id is not None])
    )).all())
    sectors = world.sectors(db)
    return templates.TemplateResponse("admin/events.html", {
        "request": request, "player": admin, "event": event, "catalog": catalog, "creating": creating,
        "entries": db.scalars(select(GlobalEvent).order_by(GlobalEvent.id.desc())).all(),
        "sectors": [sector for sector in sectors if world.location_available(db, sector.key, "enterprises")],
        "sector_names": {sector.key: sector.name for sector in sectors},
        "resources": resource_definitions(), "builds": builds, "build_names": build_names, "stage": events.stage, "now": world.utc_now(),
        "stage_names": events.STAGES, "display_date": news.display_date, "preview": events.notification_text(event) if event else "",
        "stats": events.statistics(db, event.id) if event else None,
        "listings": [(listing.id, listing.item_template.name) for listing in db.scalars(
            select(ShopItem).order_by(ShopItem.id)) if listing.item_template],
        "rewards": reward_rows(db, event.id) if event else [],
        "audit": db.scalars(select(GlobalEventAudit).where(GlobalEventAudit.event_id == event.id)
                            .order_by(GlobalEventAudit.id.desc())).all() if event else [],
    })


@router.post("/admin/events", status_code=201)
@router.patch("/admin/events/{event_id}")
def save_event(body: events.Draft, event_id: int | None = None, db: Session = DB, admin: User = ADMIN):
    event = events.save_draft(db, admin, body, event_id)
    db.commit()
    return {"id": event.id}


@router.post("/admin/events/image")
def upload_image(image: UploadFile = File(...), admin: User = ADMIN):
    prefix = events.IMAGE_PREFIX + "events/"
    return {"image_url": news.store_image(image, directory=events.STATIC / Path(prefix.removeprefix("/static/")),
                                        prefix=prefix)}


class StageArtwork(BaseModel):
    stage_images: dict[str, str]


@router.patch("/admin/events/{event_id}/enterprises/{enterprise_id}/images")
def edit_stage_artwork(event_id: int, enterprise_id: int, body: StageArtwork,
                       db: Session = DB, admin: User = ADMIN):
    images = events.update_stage_images(db, event_id, enterprise_id, body.stage_images, admin)
    db.commit()
    return {"stage_images": images}


@router.post("/admin/events/{event_id}/start")
def start(event_id: int, body: Confirmation, db: Session = DB, admin: User = ADMIN):
    confirm(body)
    event = events.start(db, event_id, admin)
    db.commit()
    return {"status": event.status}


@router.post("/admin/events/{event_id}/cancel")
def cancel(event_id: int, body: Confirmation, db: Session = DB, admin: User = ADMIN):
    confirm(body)
    events.cancel(db, event_id, admin)
    db.commit()
    return {"status": "CANCELLED"}


@router.get("/admin/events/{event_id}/statistics")
def admin_statistics(event_id: int, db: Session = DB, admin: User = ADMIN):
    current(db)
    event = events.event_or_404(db, event_id, admin=True)
    return events.statistics(db, event.id)


@router.post("/admin/events/{event_id}/rewards/preview")
def preview_rewards(event_id: int, body: events.RewardPlan, db: Session = DB, admin: User = ADMIN):
    current(db)
    return events.reward_preview(db, events.event_or_404(db, event_id, admin=True), body)


def reward_rows(db, event_id):
    return db.scalars(select(EventReward).where(EventReward.event_id == event_id).order_by(EventReward.id)).all()


@router.get("/admin/events/{event_id}/rewards")
def rewards(event_id: int, db: Session = DB, admin: User = ADMIN):
    events.event_or_404(db, event_id, admin=True)
    return reward_rows(db, event_id)


@router.post("/admin/events/{event_id}/rewards/issue")
def issue(event_id: int, body: IssueRequest, db: Session = DB, admin: User = ADMIN):
    confirm(body)
    current(db)
    world.lock_world(db)
    event = events.event_or_404(db, event_id, admin=True)
    if event.status == "REWARDED":
        return {"status": event.status}
    if event.status != "COMPLETED":
        raise HTTPException(409, "Подія ще не завершена.")
    if body.plan is not None:
        if not reward_rows(db, event.id):
            events.queue_rewards(db, event, body.plan, admin)
    elif not reward_rows(db, event.id):
        raise HTTPException(409, "Спочатку підтвердь план нагород.")
    db.commit()
    identifiers = [row.id for row in reward_rows(db, event_id) if row.status != "ISSUED"]
    db.commit()
    for identifier in identifiers:
        world.lock_world(db)
        reward = db.get(EventReward, identifier, populate_existing=True)
        if reward.status == "ISSUED":
            db.commit()
            continue
        try:
            with db.begin_nested():
                reward.status = "PROCESSING"
                events.credit_reward(db, event, reward, admin)
        except (HTTPException, SQLAlchemyError) as exc:
            reward.status = "FAILED"
            reward.error = exc.detail if isinstance(exc, HTTPException) else "Помилка транзакції під час видачі."
        db.commit()
    world.lock_world(db)
    event = events.event_or_404(db, event_id, admin=True)
    if all(row.status == "ISSUED" for row in reward_rows(db, event_id)):
        if event.status != "REWARDED":
            event.status, event.rewarded_at = "REWARDED", world.utc_now()
            events.audit(db, event, admin, "REWARDED", event.rewarded_at)
    db.commit()
    return {"status": event.status, "rewards": reward_rows(db, event_id)}
