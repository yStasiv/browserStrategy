from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel, StrictInt

from backend.auth import playable_users, session_player
from backend import database, models
from backend.auth import get_current_user
from backend.services import player_moderation
from backend.services.character_profile import dashboard, hero_state
from backend.routers.item import ITEM_TYPES
from backend.services.guild_experience import hero_xp_threshold
from backend.services.hero_attributes import SPENDABLE_ATTRIBUTES
from backend.services.hero_equipment import change_equipment, lock_hero
from backend.services.hero_army import save_roster
from backend.engine.battle_service import get_active_battle_id

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


class PlayerHelper:

    @staticmethod
    def experience_needed_for_next_level(level: int) -> int | None:
        return hero_xp_threshold(level)


@router.get("/player_info")
async def player_info(
    id: int, request: Request, db: Session = Depends(database.get_db)
):
    viewer = session_player(request, db)
    player = playable_users(db).filter(models.User.id == id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Персонажа не знайдено.")

    # Отримуємо рейтинг гравця
    player_rating = db.query(models.PlayerRating).filter(
        models.PlayerRating.user_id == player.id
    ).first()

    if not player_rating:
        # Якщо рейтингу ще немає, створюємо новий
        player_rating = models.PlayerRating(user_id=player.id)
        db.add(player_rating)
        db.commit()
        db.refresh(player_rating)

    profile = dashboard(db, player, PlayerHelper.experience_needed_for_next_level(player.level))
    profile["resources"] = [resource for resource in profile["resources"] if not resource["conditional"]]
    show_account_status = player_moderation.can_view_account_status(viewer)
    return templates.TemplateResponse(
        "payer_info.html",
        {
            "request": request,
            "player": player,
            "profile": profile,
            "item_types": ITEM_TYPES,
            "read_only": True,
            "nav_player": viewer,
            "player_rating": player_rating,
            "show_account_status": show_account_status,
            "can_moderate": player_moderation.can_moderate(viewer, player),
            "can_assign_moderator": player_moderation.can_assign_moderator(viewer, player),
            "moderation_entries": [player_moderation.display_entry(event)
                                   for event in player_moderation.history(db, player.id)] if show_account_status else [],
        },
    )


class PlayerRotes(PlayerHelper):

    @router.get("/player")
    async def character_page(request: Request, db: Session = Depends(database.get_db)):
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Увійди до гри.")

        next_level_exp = PlayerHelper().experience_needed_for_next_level(user.level)

        return templates.TemplateResponse("player.html", {
            "request": request, "player": user, "profile": dashboard(db, user, next_level_exp),
            "item_types": ITEM_TYPES,
        })

    @router.post("/update-attribute", response_class=RedirectResponse)
    async def update_attribute(
        request: Request,
        attribute: str = Form(...),
        db: Session = Depends(database.get_db),
    ):
        column = SPENDABLE_ATTRIBUTES.get(attribute)
        if column is None:
            raise HTTPException(400, "Невідома характеристика.")

        user = hero_player(request, db)
        lock_hero(db, user)
        if (user.pending_attribute_points or 0) <= 0:
            raise HTTPException(400, "Немає вільних очок характеристик.")

        allocations = dict(user.attribute_allocations)
        allocations[column] = allocations.get(column, 0) + 1
        setattr(user, column, (getattr(user, column) or 0) + 1)
        user.attribute_allocations = allocations
        user.pending_attribute_points -= 1
        db.commit()
        return RedirectResponse(url="/player", status_code=303)

    @router.post("/reset-attributes", response_class=RedirectResponse)
    async def reset_attributes(request: Request, db: Session = Depends(database.get_db)):
        user = hero_player(request, db)
        lock_hero(db, user)
        for column, points in user.attribute_allocations.items():
            setattr(user, column, getattr(user, column) - points)
        user.pending_attribute_points = (user.pending_attribute_points or 0) + sum(user.attribute_allocations.values())
        user.attribute_allocations = {}
        db.commit()
        return RedirectResponse(url="/player", status_code=303)


def hero_player(request, db):
    player = session_player(request, db)
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    return player


class HeroEquip(BaseModel):
    slot: str
    item_id: StrictInt | None


class HeroArmyUpdate(BaseModel):
    counts: dict[str, StrictInt]


@router.get("/hero/state")
def read_hero_state(request: Request, db: Session = Depends(database.get_db)):
    return hero_state(db, hero_player(request, db))


@router.post("/hero/equip")
def equip_hero(body: HeroEquip, request: Request, db: Session = Depends(database.get_db)):
    player = hero_player(request, db)
    lock_hero(db, player)
    if get_active_battle_id(db, player.id) is not None:
        raise HTTPException(409, "Під час бою спорядження змінити неможливо.")
    change_equipment(db, player, slot=body.slot, item_id=body.item_id, remove=body.item_id is None)
    db.commit()
    return hero_state(db, player)


@router.post("/hero/army/update")
def update_hero_army(body: HeroArmyUpdate, request: Request, db: Session = Depends(database.get_db)):
    player = hero_player(request, db)
    save_roster(db, player, body.counts)
    return hero_state(db, player)


@router.get("/player_info/transfers")
def player_transfer_protocol(id: int, request: Request, db: Session = Depends(database.get_db)):
    viewer = session_player(request, db)
    player = playable_users(db).filter(models.User.id == id).first()
    if player is None:
        raise HTTPException(404, "Персонажа не знайдено.")
    receipt = models.RewardTransaction
    entries = db.query(receipt).filter(receipt.recipient_id == player.id).order_by(
        receipt.created_at.desc(), receipt.id.desc(),
    ).all()
    combined = [(entry.created_at, entry, None) for entry in entries]
    combined.extend((event.created_at, None, player_moderation.display_entry(event))
                    for event in player_moderation.history(db, player.id))
    combined.sort(key=lambda row: row[0], reverse=True)
    return templates.TemplateResponse("player_transfers.html", {
        "request": request, "player": player, "nav_player": viewer,
        "entries": combined,
    })
