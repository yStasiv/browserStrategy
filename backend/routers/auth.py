# backend/routers/auth.py
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.auth import playable_users
from backend.engine.data import faction_key
from backend.services.castle_buildings import grant_starter_buildings

from .. import database, models
from ..utils import hash_password, setup_logger, verify_password

logger = setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


class AuthHelper:
    def add_unit_types(db: Session):
        """Add unit types for all fractions"""
        elfe_unit_types = [
            {
                "name": "Baby",
                "level_required": 1,
                "fraction": "elfe",
                "max_quantity": 17,
                "icon_url": "../static/images/frankenstein.png",
            },
            {
                "name": "Junior",
                "level_required": 2,
                "fraction": "elfe",
                "max_quantity": 12,
                "icon_url": "../static/images/frankenstein.png",
            },
            {
                "name": "Adult",
                "level_required": 5,
                "fraction": "elfe",
                "max_quantity": 8,
                "icon_url": "../static/images/frankenstein.png",
            },
            {
                "name": "Old",
                "level_required": 8,
                "fraction": "elfe",
                "max_quantity": 2,
                "icon_url": "../static/images/frankenstein.png",
            },
        ]

        green_elfe_unit_types = [
            {
                "name": "green_Baby",
                "level_required": 1,
                "fraction": "undergroundElves",
                "max_quantity": 19,
                "icon_url": "../static/images/frankenstein.png",
            },
            {
                "name": "green_Junior",
                "level_required": 2,
                "fraction": "undergroundElves",
                "max_quantity": 10,
                "icon_url": "../static/images/frankenstein.png",
            },
            {
                "name": "green_Adult",
                "level_required": 5,
                "fraction": "undergroundElves",
                "max_quantity": 9,
                "icon_url": "../static/images/frankenstein.png",
            },
            {
                "name": "green_Old",
                "level_required": 8,
                "fraction": "undergroundElves",
                "max_quantity": 3,
                "icon_url": "../static/images/frankenstein.png",
            },
        ]
        for unit_types in [elfe_unit_types, green_elfe_unit_types]:
            for unit in unit_types:
                unit_type = models.UnitType(
                    name=unit["name"],
                    level_required=unit["level_required"],
                    fraction=unit["fraction"],
                    max_quantity=unit["max_quantity"],
                    icon_url=unit["icon_url"],
                )
                db.add(unit_type)
        db.commit()

    def get_default_unit_types(fraction: str, db: Session):
        """Get unit types by fraction"""
        return (
            db.query(models.UnitType).filter(models.UnitType.fraction == fraction).all()
        )

    def set_default_user_units(user: models.User, db: Session) -> None:
        """Set default user unit values"""
        default_units = AuthHelper.get_default_unit_types(user.fraction, db)

        for unit in default_units:
            unit_type = (
                db.query(models.UnitType)
                .filter(models.UnitType.name == unit.name)
                .first()
            )
            if unit_type:  # check if unit was added to avoid duplicates
                existing_user_unit = (
                    db.query(models.UserUnit)
                    .filter(
                        models.UserUnit.user_id == user.id,
                        models.UserUnit.unit_type_id == unit_type.id,
                    )
                    .first()
                )
                if not existing_user_unit:
                    user_unit = models.UserUnit(
                        user_id=user.id,
                        unit_type_id=unit_type.id,
                        quantity=0,  # unit.max_quantity
                    )
                    db.add(user_unit)
            db.commit()


class AuthRotes:
    @router.post("/register")
    async def register(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        fraction: str = Form(...),
        gender: Literal["male", "female"] = Form("male"),
        db: Session = Depends(database.get_db),
    ):
        fraction = {"elves": "elfe", "underground_elves": "undergroundElves"}.get(faction_key(fraction))
        if fraction is None:
            raise HTTPException(422, "Обери доступну фракцію.")
        # Перевіряємо чи існує користувач
        existing_user = (
            db.query(models.User).filter(models.User.username == username).first()
        )
        if existing_user:
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "Користувач з таким ім'ям вже існує"},
            )

        # Хешуємо пароль
        hashed_password = hash_password(password)

        # Створюємо нового користувача
        new_user = models.User(
            username=username, password=hashed_password, fraction=fraction, gender=gender,
        )
        db.add(new_user)
        db.flush()
        grant_starter_buildings(db, new_user)

        # Додаємо початкові юніти
        unit_types = AuthHelper.get_default_unit_types(fraction, db)
        for unit_type in unit_types:
            user_unit = models.UserUnit(
                user_id=new_user.id, unit_type_id=unit_type.id, quantity=0
            )
            db.add(user_unit)

        db.commit()

        return RedirectResponse(url="/login", status_code=303)

    @router.post("/login")
    def login(
        # request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(database.get_db),
    ):
        user = playable_users(db).filter(models.User.username == username).first()
        if not user or not user.password or not verify_password(password, user.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        response = RedirectResponse(url="/player", status_code=303)

        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)

        user.session_id = session_id
        db.commit()

        return response

    @router.post("/logout")
    def logout(request: Request, db: Session = Depends(database.get_db)):
        session_id = request.cookies.get("session_id")
        if session_id:
            db.execute(update(models.User).where(models.User.session_id == session_id).values(session_id=None))
            db.commit()

        response = RedirectResponse(url="/login", status_code=303, headers={"Cache-Control": "no-store"})
        response.delete_cookie("session_id")
        response.delete_cookie("username")
        return response

    @router.get("/")
    async def root(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @router.get("/register")
    async def show_register_form(request: Request):
        return templates.TemplateResponse("register.html", {"request": request})

    @router.get("/login")
    async def show_login_form(request: Request):
        return templates.TemplateResponse("login.html", {"request": request})
