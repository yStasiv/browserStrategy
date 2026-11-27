# backend/routers/auth.py
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import playable_users, require_unblocked, session_player
from backend.engine.data import faction_key
from backend.services.castle_buildings import grant_starter_buildings
from backend.services.hero_equipment import lock_hero
from backend.services.map_config import marker_position
from backend.services.nicknames import username_match, validation_error

from .. import database, models
from ..utils import hash_password, setup_logger, verify_password

logger = setup_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


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
        username = username.strip()
        if error := validation_error(db, username):
            return templates.TemplateResponse("register.html", {"request": request, "error": error}, status_code=422)

        # Хешуємо пароль
        hashed_password = hash_password(password)

        # Створюємо нового користувача
        map_x, map_y = marker_position("Castle")
        new_user = models.User(
            username=username, password=hashed_password, fraction=fraction, gender=gender,
            map_x=map_x, map_y=map_y,
            mind=1 if fraction == "elfe" else 0,
            melee_attack=1 if fraction == "undergroundElves" else 0,
        )
        db.add(new_user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return templates.TemplateResponse("register.html", {
                "request": request, "error": "Цей нікнейм уже зайнято.",
            }, status_code=409)
        grant_starter_buildings(db, new_user)

        db.commit()

        return RedirectResponse(url="/login", status_code=303)

    @router.post("/login")
    def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(database.get_db),
    ):
        user = playable_users(db).filter(username_match(username)).first()
        if not user or not user.password or not verify_password(password, user.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        session_id = str(uuid.uuid4())
        try:
            require_unblocked(user)
            result = db.execute(update(models.User).where(
                models.User.id == user.id, models.User.is_active.is_(True), models.User.ban_reason.is_(None),
                models.User.username == user.username, models.User.nickname_reset_from == user.nickname_reset_from,
            ).values(session_id=session_id))
            if not result.rowcount:
                db.refresh(user)
                require_unblocked(user)
                raise HTTPException(403, "Вхід недоступний.")
        except HTTPException as exc:
            db.rollback()
            return templates.TemplateResponse("login.html", {"request": request, "error": exc.detail},
                                              status_code=exc.status_code, headers={"Cache-Control": "no-store"})
        destination = "/choose-nickname" if user.nickname_reset_from is not None else "/player"
        db.commit()
        response = RedirectResponse(url=destination, status_code=303)
        response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax")
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

@router.get("/choose-nickname")
def choose_nickname_page(request: Request, db: Session = Depends(database.get_db)):
    player = session_player(request, db, allow_nickname_reset=True)
    if player is None:
        return RedirectResponse("/login", status_code=303)
    if player.nickname_reset_from is None:
        return RedirectResponse("/player", status_code=303)
    return nickname_form(request, player)


def nickname_form(request, player, *, error=None, status=200):
    return templates.TemplateResponse("choose_nickname.html", {
        "request": request, "temporary_name": player.username, "error": error,
    }, status_code=status, headers={"Cache-Control": "no-store"})


@router.post("/choose-nickname")
def choose_nickname(request: Request, username: str = Form(...), db: Session = Depends(database.get_db)):
    player = session_player(request, db, allow_nickname_reset=True)
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    lock_hero(db, player)
    require_unblocked(player)
    if player.session_id != request.cookies.get("session_id"):
        raise HTTPException(401, "Увійди до гри.")
    if player.nickname_reset_from is None:
        raise HTTPException(409, "Заміна нікнейму зараз не потрібна.")
    username = username.strip()
    if error := validation_error(db, username):
        return nickname_form(request, player, error=error, status=422)
    player.username = username
    player.nickname_reset_from = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return nickname_form(request, player, error="Цей нікнейм уже зайнято.", status=409)
    return RedirectResponse("/player", status_code=303, headers={"Cache-Control": "no-store"})


def account_settings_form(request, player, *, error=None, updated=False, status=200):
    return templates.TemplateResponse("account_settings.html", {
        "request": request, "player": player, "error": error, "updated": updated,
    }, status_code=status, headers={"Cache-Control": "no-store"})


@router.get("/settings")
def account_settings(request: Request, updated: bool = False, db: Session = Depends(database.get_db)):
    player = session_player(request, db)
    if player is None:
        return RedirectResponse("/login", status_code=303, headers={"Cache-Control": "no-store"})
    return account_settings_form(request, player, updated=updated)


@router.post("/settings/password")
def change_account_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db),
):
    player = session_player(request, db)
    if player is None:
        raise HTTPException(401, "Увійди до гри.")
    if not player.password or not verify_password(current_password, player.password):
        return account_settings_form(request, player, error="Поточний пароль неправильний.", status=400)
    if len(new_password) < 8 or len(new_password.encode("utf-8")) > 72:
        return account_settings_form(request, player, error="Новий пароль має містити від 8 символів і до 72 байтів.",
                                     status=422)
    if new_password != confirm_password:
        return account_settings_form(request, player, error="Новий пароль і підтвердження не збігаються.",
                                     status=422)
    session_id = str(uuid.uuid4())
    result = db.execute(update(models.User).where(
        models.User.id == player.id,
        models.User.session_id == request.cookies.get("session_id"),
        models.User.password == player.password,
        models.User.is_active.is_(True),
        models.User.ban_reason.is_(None),
        models.User.nickname_reset_from.is_(None),
    ).values(password=hash_password(new_password), session_id=session_id))
    if not result.rowcount:
        db.rollback()
        raise HTTPException(409, "Сесія змінилася. Увійди ще раз.")
    db.commit()
    response = RedirectResponse("/settings?updated=1", status_code=303, headers={"Cache-Control": "no-store"})
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")
    return response
