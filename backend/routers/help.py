from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from backend import database, models

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

@router.get("/help", response_class=HTMLResponse)
async def help_page(
    request: Request,
    db: Session = Depends(database.get_db)
):
    # Отримуємо користувача з сесії
    user_session_id = request.cookies.get("session_id")
    user = None
    if user_session_id:
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    
    return templates.TemplateResponse(
        "help.html",
        {
            "request": request,
            "user": user
        }
    ) 