# backend/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend import database, utils
from .routers import auth, character, castle, char_tasks

logger = utils.setup_logger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

db = database.init_db()

# Включаємо роутери
app.include_router(auth.router)
app.include_router(character.router)
app.include_router(castle.router)
app.include_router(char_tasks.router)


# TODO: Run this just one time when app start
# @app.on_event("startup")
# async def startup_event(): 
#     # Підключення до бази даних
#     db = database.SessionLocal()
#     try: 
#         # Виклик методу під час запуску 
#         auth.AuthHelper.add_unit_types(db)
#         logger.info("Unit types added successfully.") 
#     except Exception as e: 
#         logger.error(f"An error occurred while adding unit types: {e}") 
#     finally: 
#         db.close()

# if __name__ == "__main__": 
#     uvicorn.run(app, host="0.0.0.0", port=8000)