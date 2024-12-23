from fastapi import APIRouter, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from backend import models, database, utils

logger = utils.setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class CharacterHelper:

    @staticmethod
    def experience_needed_for_next_level(level: int) -> int:
        """Обчислює необхідний досвід для досягнення наступного рівня."""
        if level >= 8:
            return None  # Гравець досяг максимального рівня
        base_experience = 1000
        return int(base_experience * (1.3 ** (level - 1)))
     
    @staticmethod
    def update_user_level(user: models.User, db: Session) -> None:
        """Get user exp, check if lvl is correct and up lvl if needed"""
        next_level_exp = CharacterHelper.experience_needed_for_next_level(user.level)
        
        if next_level_exp is None:
            # Якщо досягнуто максимальний рівень, нічого не робимо
            return

        # Перевірка, чи є досвід для підвищення рівня  # TODO: перенести в функцію логування?
        while int(user.experience) >= int(next_level_exp) and int(user.level) < 8:
            user.level += 1  # Підвищуємо рівень
            # user.experience -= next_level_exp  # Віднімаємо досвід для наступного рівня
            next_level_exp = CharacterHelper.experience_needed_for_next_level(user.level)  # Обчислюємо досвід для наступного рівня
            if next_level_exp is None:
                # logger.info("Max lvl was claimed!")
                db.commit()
                break
            user.pending_attribute_points += 1
            db.commit()  # Зберігаємо зміни в базі даних

        
class CharRotes(CharacterHelper):

    @router.get("/character", response_class=HTMLResponse)
    async def character(
        request: Request,
        db: Session = Depends(database.get_db)
        ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        if not user:
                raise HTTPException(status_code=404, detail="User not found")
        
        CharacterHelper().update_user_level(user, db)
        next_level_exp = CharacterHelper().experience_needed_for_next_level(user.level)
        
        return templates.TemplateResponse("character.html", {"request": request, "user": user,  "next_level_exp": next_level_exp})
        

    @router.post("/update-attribute", response_class=RedirectResponse)
    async def update_attribute(
        request: Request,
        attribute: str = Form(...),
        db: Session = Depends(database.get_db)
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")

        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.pending_attribute_points <= 0:
            raise HTTPException(status_code=400, detail="No pending attribute points available")
        
        attribute_update = { 
            "strength": lambda u: setattr(u, "strength", u.strength + 1), 
            "defense": lambda u: setattr(u, "defense", u.defense + 1), 
            "initiative": lambda u: setattr(u, "initiative", u.initiative + 1) 
            } 
        update_func = attribute_update.get(attribute, None) 
        if update_func is not None: 
            update_func(user) 
            user.pending_attribute_points -= 1 
            db.commit()

        # if attribute == "strength":
        #     user.strength += 1
        # elif attribute == "defense":
        #     user.defense += 1
        # elif attribute == "initiative":
        #     user.initiative += 1
        else:
            logger.error(HTTPException(status_code=400, detail="Invalid attribute"))
        #     pass

        # user.pending_attribute_points -= 1
        # db.commit()

        return RedirectResponse(url="/character", status_code=303)
