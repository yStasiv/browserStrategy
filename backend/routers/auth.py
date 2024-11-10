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

class AuthRotes:
    @router.post("/register")
    async def register(
        # request: Request,
        username: str = Form(...),
        password: str = Form(...),
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
            level=1, 
            gold=0,  
            wood=0, 
            stone=0,
            )
        db.add(new_user)
        db.commit()

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