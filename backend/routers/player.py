from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel, StrictInt

from backend.auth import playable_users, session_player
from backend import database, models, utils
from backend.auth import get_current_user
from backend.services.character_profile import dashboard, hero_state
from backend.services.hero_equipment import change_equipment, lock_hero
from backend.services.hero_army import save_roster
from backend.engine.battle_service import get_active_battle_id

logger = utils.setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


class PlayerHelper:

    @staticmethod
    def experience_needed_for_next_level(level: int) -> int:
        """Розрахунок необхідного досвіду для наступного рівня"""
        if level >= 8:  # Максимальний рівень
            return None

        # Формула розрахунку досвіду
        exp_requirements = {
            1: 1000,  # для досягнення 2 рівня
            2: 3000,  # для досягнення 3 рівня
            3: 6000,  # для досягнення 4 рівня
            4: 10000,  # для досягнення 5 рівня
            5: 15000,  # для досягнення 6 рівня
            6: 21000,  # для досягнення 7 рівня
            7: 28000,  # для досягнення 8 рівня
        }
        return int(exp_requirements.get(level, 1))

    @staticmethod
    def update_user_level(user: models.User, db: Session) -> None:
        """Get user exp, check if lvl is correct and up lvl if needed"""
        next_level_exp = PlayerHelper.experience_needed_for_next_level(user.level)

        if next_level_exp is None:
            # Якщо досягнуто максимальний рівень, нічого не робимо
            return

        # Перевірка, чи є досвід для підвищення рівня  # TODO: перенести в функцію логування?
        while int(user.experience) >= int(next_level_exp) and int(user.level) < 8:
            user.level += 1  # Підвищуємо рівень
            # user.experience -= next_level_exp  # Віднімаємо досвід для наступного рівня
            next_level_exp = PlayerHelper.experience_needed_for_next_level(
                user.level
            )  # Обчислюємо досвід для наступного рівня
            if next_level_exp is None:
                # logger.info("Max lvl was claimed!")
                db.commit()
                break
            user.pending_attribute_points += 1
            db.commit()  # Зберігаємо зміни в базі даних


@router.get("/player_info")
async def player_info(
    id: int, request: Request, db: Session = Depends(database.get_db)
):
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
    return templates.TemplateResponse(
        "payer_info.html",
        {
            "request": request,
            "player": player,
            "profile": profile,
            "public_guilds": [dict(guild, route=None, requirements=None) for guild in profile["guilds"]],
            "read_only": True,
            "nav_player": session_player(request, db),
            "player_rating": player_rating
        },
    )


class PlayerRotes(PlayerHelper):

    @router.get("/player")
    async def character_page(request: Request, db: Session = Depends(database.get_db)):
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Увійди до гри.")

        PlayerHelper().update_user_level(user, db)
        next_level_exp = PlayerHelper().experience_needed_for_next_level(user.level)

        return templates.TemplateResponse("player.html", {
            "request": request, "player": user, "profile": dashboard(db, user, next_level_exp),
        })

    @router.post("/update-attribute", response_class=RedirectResponse)
    async def update_attribute(
        request: Request,
        attribute: str = Form(...),
        db: Session = Depends(database.get_db),
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Увійди до гри.")

        user = session_player(request, db)
        if not user:
            raise HTTPException(status_code=404, detail="Персонажа не знайдено.")

        if user.pending_attribute_points <= 0:
            raise HTTPException(
                status_code=400, detail="Немає вільних очок характеристик."
            )

        attribute_update = {
            "stamina": lambda u: setattr(u, "stamina", u.stamina + 1),
            "energy": lambda u: setattr(u, "energy", u.energy + 1),
            "agility": lambda u: setattr(u, "agility", u.agility + 1),
            "mind": lambda u: setattr(u, "mind", u.mind + 1),
        }
        update_func = attribute_update.get(attribute, None)
        if update_func is not None:
            update_func(user)
            user.pending_attribute_points -= 1
            db.commit()

        else:
            logger.error(HTTPException(status_code=400, detail="Invalid attribute"))

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
    player = playable_users(db).filter(models.User.id == id).first()
    if player is None:
        raise HTTPException(404, "Персонажа не знайдено.")
    receipt = models.RewardTransaction
    entries = db.query(receipt).filter(receipt.recipient_id == player.id).order_by(
        receipt.created_at.desc(), receipt.id.desc(),
    ).all()
    return templates.TemplateResponse("player_transfers.html", {
        "request": request, "player": player, "nav_player": session_player(request, db),
        "entries": entries,
    })
