# backend/routers/auth.py
import uuid
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from .. import database, models
from ..utils import verify_password, hash_password

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class AuthHelper():
    def add_unit_types(db):
        """Add unit types for all fractions"""
        elfe_unit_types = [
            {"name": "Baby", "level_required": 1, "max_units": 17},
            {"name": "Junior", "level_required": 2, "max_units": 12},
            {"name": "Adult", "level_required": 5, "max_units": 8},
            {"name": "Old", "level_required": 8, "max_units": 2}
        ]

        green_elfe_unit_types =[
            {"name": "green_Baby", "level_required": 1, "max_units": 19},
            {"name": "green_Junior", "level_required": 2, "max_units": 10},
            {"name": "green_Adult", "level_required": 5, "max_units": 9},
            {"name": "green_Old", "level_required": 8, "max_units": 3}
        ]
        for unit_types in [elfe_unit_types, green_elfe_unit_types]:
            for unit in unit_types:
                unit_type = models.UnitType(name=unit["name"], level_required=unit["level_required"], max_units=unit["max_units"])
                db.add(unit_type)

        db.commit()

    def get_default_unit_types(db: Session, fraction: str = ""):
        """Get unit types by fraction"""
        return db.query(models.UnitType).filter(models.User.fraction == fraction).all()

    def set_default_user_units(user: models.User, db: Session) -> None:
        """Set default user unit values"""
        default_units = AuthHelper.get_default_unit_types(user.fraction, db)

        for unit in default_units:
            unit_type = db.query(models.UnitType).filter(models.UnitType.name == unit["name"]).first()
            if unit_type:
                user_unit = models.UserUnit(
                    user_id=user.id,
                    unit_type_id=unit_type.id,
                    quantity=unit["quantity"]
                )
                db.add(user_unit)

        db.commit()

class AuthRotes:
    @router.post("/register")
    async def register(
        # request: Request,
        username: str = Form(...),
        password: str = Form(...),
        fraction: str = Form(...),
        db: Session = Depends(database.get_db)
    ):
        # Перевірка на наявність користувача
        existing_user = db.query(models.User).filter(models.User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")
        
        # Створення нового користувача
        new_user = models.User(
            username=username, 
            password=hash_password(password), 
            fraction=fraction,
            level=1, 
            gold=0,  
            wood=0, 
            stone=0,
            )
        db.add(new_user)
        db.commit()

        AuthHelper.add_unit_types(db)  # TODO: move from there...

        AuthHelper.set_default_user_units(new_user, db)

        return RedirectResponse(url="/", status_code=303)


    @router.post("/login")
    def login(
        # request: Request, 
        username: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(database.get_db)
    ):
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user or not verify_password(password, user.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        response = RedirectResponse(url="/character", status_code=303)

        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)
        response.set_cookie(key="username", value=user.username)  # Зберігаємо ім'я в cookie (можна використовувати сесії або токени)

        user.session_id = session_id
        db.commit()

        return response
    
    @router.post("/logout")
    async def logout(response: Response):
        # Очищення куків (включаючи сесію)
        response.delete_cookie("session_id")
        
        # Перенаправлення користувача на головну сторінку або сторінку логіну після виходу
        return RedirectResponse(url="/", status_code=303)

    @router.get("/")
    async def root(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})