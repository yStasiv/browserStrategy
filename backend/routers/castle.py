from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from .. import models, database
from utils import setup_logger

logger = setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class CastleHelpers:

    def get_available_units(user: models.User, db: Session):
        """Return available types of units related to user lvl"""
        logger.info(f"Fetching available units for user id {user.id}, level {user.level}, fraction {user.fraction}")
        unit_types = db.query(models.UnitType).filter(
            models.UnitType.level_required <= user.level,
            models.UnitType.fraction == user.fraction                                          
        ).all()

        if not unit_types: 
            logger.warning(f"No units found for user id {user.id}, level {user.level}, fraction {user.fraction}")
        else:
            for unit in unit_types:
                logger.info(f"Found unit: {unit.name}, level_required: {unit.level_required}")

        available_units = [ 
            { 
                "name": unit.name, 
                "max_units": unit.max_quantity, # Припускаючи, що у моделі UnitType є поле max_units
                "icon_url": unit.icon_url # Припускаючи, що у моделі UnitType є поле icon_url
            } 
             for unit in unit_types 
        ]
        unique_units = {unit['name']: unit for unit in available_units}.values()       
        return list(unique_units)

    def add_units_to_user(user: models.User, unit_type_id: int, quantity: int, db: Session):
        """Add and save units for a user"""
        unit_type = db.query(models.UnitType).filter(models.UnitType.id == unit_type_id).first()
        
        # Перевірка максимального ліміту
        if quantity < 0 or quantity > unit_type.max_quantity:
            logger.error(f"Unit '{unit_type.name}' quantity should be between 0 and {unit_type.max_quantity}, actual quantity is {quantity}")
            return
        
        user_unit = db.query(models.UserUnit).filter(
            models.UserUnit.user_id == user.id, models.UserUnit.unit_type_id == unit_type_id
        ).first()

        if user_unit:
            user_unit.quantity = quantity  # Оновлюємо кількість
        else:
            user_unit = models.UserUnit(user_id=user.id, unit_type_id=unit_type_id, quantity=quantity)
            db.add(user_unit)
        
        db.commit()

class CastleRotes(CastleHelpers):
    # Сторінка замку
    @router.get("/castle", response_class=HTMLResponse)
    def castle_page(request: Request, db: Session = Depends(database.get_db)):
        
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        available_units = CastleHelpers.get_available_units(user, db)  # Отримуємо доступні юніти
        # Отримуємо вже набрані війська
        user_units = db.query(models.UserUnit).filter(models.UserUnit.user_id == user.id).all()
        user_units_dict = {unit.unit_type.name: unit.quantity for unit in user_units}

        
        return templates.TemplateResponse("castle.html", {
            "request": request,
            "user": user,
            "available_units": available_units,
            "user_units": user_units_dict  # Передаємо дані про війська користувача на фронтенд
        })
    

    # Обробка пост-запиту для набору військ
    @router.post("/castle", response_class=HTMLResponse)
    async def add_units(request: Request, db: Session = Depends(database.get_db)):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()

        form_data = await request.form()
        
        for unit in form_data:
            unit_name = unit
            try:
                quantity = int(form_data[unit])
            except ValueError as e:
                logger.error(f"{e}, action was ignored")
                quantity = 0
            unit_type = db.query(models.UnitType).filter(models.UnitType.name == unit_name).first()
            
            if unit_type and quantity > 0:
                CastleHelpers.add_units_to_user(user, unit_type.id, quantity, db)

            available_units = CastleHelpers.get_available_units(user, db)  # Отримуємо доступні юніти

        user_units = db.query(models.UserUnit).filter(models.UserUnit.user_id == user.id).all()
        user_units_dict = {unit.unit_type.name: unit.quantity for unit in user_units}


        return templates.TemplateResponse("castle.html", {
            "request": request,
            "user": user,
            "available_units": available_units,
            "user_units": user_units_dict
        })