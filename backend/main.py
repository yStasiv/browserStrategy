import os
import uuid
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from backend import models, database

app = FastAPI()

# Створення бази даних, якщо її немає
database.init_db()

# Підключаємо статичні файли для FastAPI
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Шаблони
templates = Jinja2Templates(directory="frontend/templates")

# Налаштування бази даних
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Налаштування хешування паролів
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/register")
async def register(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Перевірка на наявність користувача
    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    # Хешування пароля перед збереженням
    hashed_password = hash_password(password)

    # Створення нового користувача
    new_user = models.User(username=username, password=hashed_password, level=1, gold=0,  wood=0, stone=0 )
    db.add(new_user)
    db.commit()
    # db.refresh(new_user)

    return RedirectResponse(url="/", status_code=303)

@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
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

@app.post("/logout")
async def logout(response: Response):
    # Очищення куків (включаючи сесію)
    response.delete_cookie("session_id")
    
    # Перенаправлення користувача на головну сторінку або сторінку логіну після виходу
    return RedirectResponse(url="/", status_code=303)

@app.get("/character", response_class=HTMLResponse)
async def character(
    request: Request,
    db: Session = Depends(get_db)
    ):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
            raise HTTPException(status_code=404, detail="User not found")
    
    return templates.TemplateResponse("character.html", {"request": request, "user": user})
    
