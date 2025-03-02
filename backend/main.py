# backend/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend import database, utils
from .routers import (
    auth, character, castle, char_tasks, upload, 
    enterprise, map, admin, help, adventure_guild
)

logger = utils.setup_logger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/avatars", StaticFiles(directory="frontend/user_resourses/avatars"), name="avatars")

db = database.init_db()

logger.info("Starting application...")
logger.info("Registering routers...")
app.include_router(auth.router)
logger.info("Auth router registered")
app.include_router(character.router)
logger.info("Character router registered")
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


# TODO: Run this just one time when app start
@app.on_event("startup")
async def startup_event(): 
    # Підключення до бази даних
    db = database.SessionLocal()
    try: 
        # Виклик методу під час запуску 
        auth.AuthHelper.add_unit_types(db)
        logger.info("Unit types added successfully.") 
    except Exception as e: 
        logger.error(f"An error occurred while adding unit types: {e}") 
    finally: 
        db.close()

if __name__ == "__main__": 
    uvicorn.run(app, host="0.0.0.0", port=8000)