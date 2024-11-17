from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from .. import models, database

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class CastleHelpers:

    def get_available_units(level: int, db: Session):
        """Повертає доступні типи військ в залежності від рівня."""
        unit_types = db.query(models.UnitType).filter(models.UnitType.level_required <= level).all()
        return [unit.name for unit in unit_types]

    def add_units_to_user(user: models.User, unit_type_id: int, quantity: int, db: Session):
        """Додає одиниці війська користувачу."""
        unit_type = db.query(models.UnitType).filter(models.UnitType.id == unit_type_id).first()
        
        # Перевірка максимального ліміту
        if quantity < 0 or quantity > 10:
            raise ValueError("Кількість юнітів повинна бути між 0 та 10.")
        
        user_unit = db.query(models.UserUnit).filter(
            models.UserUnit.user_id == user.id, models.UserUnit.unit_type_id == unit_type_id
        ).first()

        if user_unit:
            user_unit.quantity += quantity  # Оновлюємо кількість
        else:
            user_unit = models.UserUnit(user_id=user.id, unit_type_id=unit_type_id, quantity=quantity)
            db.add(user_unit)
        
        db.commit()

class CastleRotes(CastleHelpers):
    # Сторінка замку
    @router.get("/castle", response_class=HTMLResponse)
    def castle_page(request: Request, db: Session = Depends(database.get_db)):


        available_units = [
        {"name": "Піхотинці", "max_units": 10, "icon_url": "../static/images/frankenstein.png"},
        {"name": "Стрільці", "max_units": 8, "icon_url": "../static/images/frankenstein.png"},
        {"name": "Кавалерія", "max_units": 5, "icon_url": "../static/images/frankenstein.png"},
        {"name": "Tester", "max_units": 1, "icon_url": "../static/images/frankenstein.png"},
    ]
    
        # Захардкоджені війська користувача
        user_units = {
            "Піхотинці": 3,
            "Стрільці": 5,
            "Кавалерія": 2,
            "Tester ": 2
        }

        
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        # available_units = CastleHelpers.get_available_units(user.level, db)  # Отримуємо доступні юніти
        # Отримуємо вже набрані війська
        # user_units = db.query(models.UserUnit).filter(models.UserUnit.user_id == user.id).all()
        # user_units_dict = {unit.unit_type.name: unit.quantity for unit in user_units}

        
        return templates.TemplateResponse("castle.html", {
            "request": request,
            "user": user,
            "available_units": available_units,
            "user_units": user_units  # Передаємо дані про війська користувача на фронтенд
        })
    

    # Обробка пост-запиту для набору військ
    @router.post("/castle", response_class=HTMLResponse)
    async def add_units(
        request: Request,
        db: Session = Depends(database.get_db),
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()

        form_data = await request.form()
        
        for unit in form_data:
            unit_name = unit
            quantity = int(form_data[unit])
            unit_type = db.query(models.UnitType).filter(models.UnitType.name == unit_name).first()
            
            if unit_type and quantity > 0:
                CastleHelpers.add_units_to_user(user, unit_type.id, quantity, db)

            available_units = CastleHelpers.get_available_units(user.level, db)  # Отримуємо доступні юніти
        print(db.query(models.UserUnit).filter(models.UserUnit.user_id == user.id).all())

        return templates.TemplateResponse("castle.html", {
            "request": request,
            "user": user,
            "available_units": available_units,
            "user_units": db.query(models.UserUnit).filter(models.UserUnit.user_id == user.id).all()
        })