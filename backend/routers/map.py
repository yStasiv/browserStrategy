from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Enterprise
from fastapi.templating import Jinja2Templates
import logging

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

logger = logging.getLogger(__name__)

def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("username")
    if username:
        return db.query(User).filter(User.username == username).first()
    return None

@router.get("/map")
async def get_map(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        return RedirectResponse(url="/")

    # Отримуємо тільки підприємства з поточного сектора
    sector_enterprises = db.query(Enterprise).filter(
        Enterprise.sector == current_user.map_sector
    ).all()

    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "user": current_user,
            "enterprises": sector_enterprises  # Передаємо відфільтровані підприємства
        }
    )
