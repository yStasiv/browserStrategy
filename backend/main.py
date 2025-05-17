# backend/main.py
import asyncio
import os

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend import database, utils
from backend.tasks import check_workers
from backend.websockets import manager

from .routers import (admin, adventure_guild, auth, castle, char_tasks,
                      enterprise, help, inventory, map, shop, player,
                      upload, item, rating)
from .routers.battles import battle

logger = utils.setup_logger(__name__)

app = FastAPI()

# Налаштування CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Дозволяємо всі джерела
    allow_credentials=True,
    allow_methods=["*"],  # Дозволяємо всі методи
    allow_headers=["*"],  # Дозволяємо всі заголовки
    expose_headers=["*"]  # Дозволяємо доступ до всіх заголовків
)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount(
    "/avatars", StaticFiles(directory="frontend/user_resourses/avatars"), name="avatars"
)

db = database.init_db()

logger.info("Starting application...")
logger.info("Registering routers...")
app.include_router(auth.router)
logger.info("Auth router registered")
app.include_router(player.router)
logger.info("Player router registered")
app.include_router(castle.router)
logger.info("Castle router registered")
app.include_router(char_tasks.router)
logger.info("Char tasks router registered")
app.include_router(upload.router)
logger.info("Upload router registered")
app.include_router(enterprise.router)
logger.info("Enterprise router registered")
app.include_router(map.router)
logger.info("Map router registered")
app.include_router(admin.router)
logger.info("Admin router registered")
app.include_router(help.router)
logger.info("Help router registered")
app.include_router(adventure_guild.router)
logger.info("Adventure Guild router registered")
app.include_router(inventory.router)
logger.info("Inventory router registered")
app.include_router(shop.router)
logger.info("Shop router registered")
app.include_router(item.router)
logger.info("Item router registered")
app.include_router(battle.router)
logger.info("Battle router registered")
app.include_router(rating.router)
logger.info("Rating router registered")


# TODO: Run this just one time when app start
@app.on_event("startup")
async def startup_event():
    # Підключення до бази даних
    db = database.SessionLocal()
    try:
        # Виклик методу під час запуску
        auth.AuthHelper.add_unit_types(db)
        logger.info("Unit types added successfully.")
        # Запускаємо фоновий процес перевірки працівників
        asyncio.create_task(check_workers())
    except Exception as e:
        logger.error(f"An error occurred while adding unit types: {e}")
    finally:
        db.close()


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
    except:
        await manager.disconnect(websocket, user_id)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
