# backend/routers/auth.py
import uuid
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from backend.routers.char_tasks import TaskHelper
from .. import database, models
from ..utils import verify_password, hash_password, setup_logger

logger = setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class AuthHelper():
    def add_unit_types(db: Session):
        """Add unit types for all fractions"""
        elfe_unit_types = [
            {"name": "Baby", "level_required": 1, "fraction":"elfe", "max_quantity": 17, "icon_url": "../static/images/frankenstein.png"},
            {"name": "Junior", "level_required": 2, "fraction":"elfe", "max_quantity": 12, "icon_url": "../static/images/frankenstein.png"},
            {"name": "Adult", "level_required": 5, "fraction":"elfe", "max_quantity": 8, "icon_url": "../static/images/frankenstein.png"},
            {"name": "Old", "level_required": 8, "fraction":"elfe", "max_quantity": 2, "icon_url": "../static/images/frankenstein.png"}
        ]

        green_elfe_unit_types =[
            {"name": "green_Baby", "level_required": 1, "fraction":"darkElfe", "max_quantity": 19, "icon_url": "../static/images/frankenstein.png"},
            {"name": "green_Junior", "level_required": 2, "fraction":"darkElfe", "max_quantity": 10, "icon_url": "../static/images/frankenstein.png"},
            {"name": "green_Adult", "level_required": 5, "fraction":"darkElfe", "max_quantity": 9, "icon_url": "../static/images/frankenstein.png"},
            {"name": "green_Old", "level_required": 8, "fraction":"darkElfe", "max_quantity": 3, "icon_url": "../static/images/frankenstein.png"}
        ]
        for unit_types in [elfe_unit_types, green_elfe_unit_types]:
            for unit in unit_types:
                unit_type = models.UnitType(
                    name=unit["name"], 
                    level_required=unit["level_required"],
                    fraction=unit["fraction"],  
                    max_quantity=unit["max_quantity"],
                    icon_url=unit["icon_url"]
                )
                db.add(unit_type)
        db.commit()

    def get_default_unit_types(fraction: str, db: Session):
        """Get unit types by fraction"""
        return db.query(models.UnitType).filter(models.UnitType.fraction == fraction).all()

    def set_default_user_units(user: models.User, db: Session) -> None:
        """Set default user unit values"""
        default_units = AuthHelper.get_default_unit_types(user.fraction, db)

        for unit in default_units:
            unit_type = db.query(models.UnitType).filter(models.UnitType.name == unit.name).first()
            if unit_type: # check if unit was added to avoid duplicates
                existing_user_unit = db.query(models.UserUnit).filter( models.UserUnit.user_id == user.id, models.UserUnit.unit_type_id == unit_type.id ).first() 
                if not existing_user_unit: 
                    user_unit = models.UserUnit( 
                        user_id=user.id, 
                        unit_type_id=unit_type.id,
                          quantity=0 # unit.max_quantity 
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

        # AuthHelper.add_unit_types(db)  # TODO: move from there...
        # AuthHelper.set_default_user_units(new_user, db)  # TODO: Think if i need it)) >>> 23.11.2024 U think that this is no needed
        db_tasks = TaskHelper.get_all_tasks(db)    
        for task in db_tasks:
            TaskHelper.update_tasks_for_users(db, task, [new_user])
            logger.info(f"Task {task.id} with title: {task.title} was added fot user {new_user.username}")

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