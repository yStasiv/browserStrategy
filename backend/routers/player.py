from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.auth import playable_users, session_player
from backend import database, models, utils
from backend.auth import get_current_user

logger = utils.setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


class PlayerHelper:

    @staticmethod
    def get_equiped_items(
        pl_equipped_items: dict, db: Session = Depends(database.get_db)
    ) -> dict:
        """Get all equiped items"""
        equipped_items = {}
        if pl_equipped_items:
            slots = {
                "helmet_id": "Шолом",
                "armor_id": "Броня",
                "boots_id": "Чоботи",
                "right_hand_id": "Права рука",
                "left_hand_id": "Ліва рука",
                "back_id": "Спина",
                "jewelry_1_id": "Прикраса 1",
                "jewelry_2_id": "Прикраса 2",
                "jewelry_3_id": "Прикраса 3",
                "jewelry_4_id": "Прикраса 4",
            }

            for slot_id, slot_name in slots.items():
                item_id = getattr(pl_equipped_items, slot_id)
                if item_id:
                    item = (
                        db.query(models.Item).filter(models.Item.id == item_id).first()
                    )
                    if item:
                        equipped_items[slot_name] = item
            return equipped_items

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
        raise HTTPException(status_code=404, detail="Character not found")

    # Отримуємо всі вдягнені предмети
    equipped_items: dict = PlayerHelper().get_equiped_items(
        pl_equipped_items=player.equipped_items, db=db
    )

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

    return templates.TemplateResponse(
        "payer_info.html",
        {
            "request": request,
            "player": player,
            "equipped_items": equipped_items if equipped_items else {},
            "player_rating": player_rating
        },
    )


class PlayerRotes(PlayerHelper):

    @router.get("/player")
    async def character_page(request: Request, db: Session = Depends(database.get_db)):
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        PlayerHelper().update_user_level(user, db)
        next_level_exp = PlayerHelper().experience_needed_for_next_level(user.level)

        # Отримуємо всі вдягнені предмети
        equipped_items: dict = PlayerHelper().get_equiped_items(
            pl_equipped_items=user.equipped_items, db=db
        )

        return templates.TemplateResponse(
            "player.html",
            {
                "request": request,
                "player": user,
                "next_level_exp": next_level_exp,
                "equipped_items": equipped_items if equipped_items else {},
            },
        )

    @router.post("/update-attribute", response_class=RedirectResponse)
    async def update_attribute(
        request: Request,
        attribute: str = Form(...),
        db: Session = Depends(database.get_db),
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")

        user = session_player(request, db)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.pending_attribute_points <= 0:
            raise HTTPException(
                status_code=400, detail="No pending attribute points available"
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
