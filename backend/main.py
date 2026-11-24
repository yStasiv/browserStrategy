# backend/main.py
import asyncio
import os
from math import ceil

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend import database, utils
from backend.auth import session_player
from backend.models import RepairJob
from backend.services.world import utc_now
from backend.tasks import check_workers
from backend.services.character_profile import resources as character_resources
from backend.websockets import manager
from backend.engine import battle_api, battle_service

from .routers import (admin, adventure_guild, auth, castle, char_tasks,
                      enterprise, help, inventory, map, shop, player,
                      item, rating)
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
app.include_router(battle_api.router)

# TODO: Run this just one time when app start
@app.middleware("http")
async def resume_active_battle(request: Request, call_next):
    path = request.url.path
    page_request = request.method == "GET" and not path.startswith(("/static/", "/avatars/", "/api/"))
    if page_request and request.cookies.get("session_id"):
        with database.SessionLocal() as session:
            player = session_player(request, session)
            if player:
                navigation = (request.headers.get("sec-fetch-mode") == "navigate"
                              or "text/html" in request.headers.get("accept", ""))
                if (navigation and (path != "/battle" or "replay" in request.query_params)
                        and battle_service.get_active_battle_id(session, player.id) is not None):
                    return RedirectResponse("/battle", status_code=303, headers={"Cache-Control": "no-store"})
                request.state.header_player = player
                job = session.get(RepairJob, player.id)
                if job is not None:
                    request.state.header_repair_seconds = max(0, ceil((job.ready_at - utc_now()).total_seconds()))
                items = character_resources(session, player)
                request.state.header_resources = (
                    [item for item in items if not item["conditional"]]
                    if path == "/player_info" else items
                )
    return await call_next(request)


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
    with database.SessionLocal() as session:
        player = session_player(websocket, session)
        authorized = player is not None and player.id == user_id
    if not authorized:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
    except:
        await manager.disconnect(websocket, user_id)

@app.get("/")
async def root():
    return {"message": "Service is running"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
