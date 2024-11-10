# backend/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from requests import Session

from backend import database, models
from .routers import auth, character, castle

app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

db = database.init_db()

# Включаємо роутери
app.include_router(auth.router)
app.include_router(character.router)
app.include_router(castle.router)
