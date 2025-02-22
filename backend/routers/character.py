from datetime import datetime
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

    @router.get("/character")
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
        
        return templates.TemplateResponse(
            "character.html",
            {
                "request": request,
                "user": user,
                "next_level_exp": next_level_exp
            }
        )

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

    # @router.get("/map", response_class=HTMLResponse)
    # async def map_page(
    #     request: Request,
    #     db: Session = Depends(database.get_db)
    #     ):
    #     user_session_id = request.cookies.get("session_id")
    #     if not user_session_id:
    #         raise HTTPException(status_code=401, detail="Not logged in")
        
    #     user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    #     if not user:
    #         raise HTTPException(status_code=404, detail="User not found")
        
    #     return templates.TemplateResponse("map.html", {"request": request, "user": user})

    @router.post("/move")
    async def move_character(
        request: Request,
        movement: dict,
        db: Session = Depends(database.get_db)
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        direction = movement.get("direction")
        
        direction_changes = {
            "e": (33.3, 0),     # Вправо
            "w": (-33.3, 0),    # Вліво
        }
        
        if direction in direction_changes:
            dx, dy = direction_changes[direction]
            
            # Обчислюємо нові координати
            new_x = max(17, min(100 - 17, user.map_x + dx))
            new_y = max(50, min(100 - 50, user.map_y + dy))
            
            # Визначаємо сектор на основі x-координати (тепер як рядок)
            if new_x < 33.3:
                new_sector = "Mountain"
            elif new_x < 66.6:
                new_sector = "Castle"
            else:
                new_sector = "Forest"
            
            # Оновлюємо позицію користувача
            user.map_x = new_x
            user.map_y = new_y
            user.map_sector = new_sector
            db.commit()
        
        return {"status": "success"}

@router.post("/move-to-sector")
async def move_to_sector(
    request: Request,
    movement: dict,
    db: Session = Depends(database.get_db)
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Перевіряємо, чи не працює зараз гравець
    if user.workplace and user.work_start_time:
        hours_worked = (datetime.now() - user.work_start_time).total_seconds() / 3600
        if hours_worked < 8:
            raise HTTPException(status_code=400, detail="You cannot leave sector while working! (8 hours not passed)")
    
    sector = str(movement.get("sector"))
    x = movement.get("x")
    y = movement.get("y")
    
    if sector in ["Mountain", "Castle", "Forest"] and x is not None and y is not None:
        user.map_sector = sector
        user.map_x = x
        user.map_y = y
        db.commit()
    
    return {"status": "success"}

    @router.get("/view-character")
    async def view_character(
        character_id: int,
        request: Request,
        db: Session = Depends(database.get_db)
    ):
        character = db.query(models.User).filter(models.User.id == character_id).first()
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        
        return templates.TemplateResponse(
            "character_view.html",
            {
                "request": request,
                "character": character
            }
        )
