from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Enterprise
from fastapi.templating import Jinja2Templates
import logging

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

logger = logging.getLogger(__name__)

@router.get("/map", response_class=HTMLResponse)
async def map_page(request: Request, db: Session = Depends(get_db)):
    logger.info("Accessing map page")
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        logger.warning("No session_id found")
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(User).filter(User.session_id == user_session_id).first()
    if not user:
        logger.warning(f"User not found for session_id: {user_session_id}")
        raise HTTPException(status_code=404, detail="User not found")

    try:
        logger.info(f"User {user.id} accessing map in sector {user.map_sector}")
        
        # Отримуємо підприємства залежно від сектору
        sector_enterprises = {
            "Forest": ["sawmill"],
            "Moutains": ["mine"],
            "Castle": ["blacksmith"]
        }
        
        available_enterprises = sector_enterprises.get(user.map_sector, [])
        enterprises = db.query(Enterprise).filter(
            Enterprise.name.in_(available_enterprises)
        ).all()
        
        logger.info(f"Found {len(enterprises)} enterprises for sector {user.map_sector}")
        for enterprise in enterprises:
            logger.info(f"Enterprise details: ID={enterprise.id}, Name={enterprise.name}, Salary={enterprise.salary}")

        return templates.TemplateResponse(
            "map.html",
            {
                "request": request,
                "user": user,
                "enterprises": enterprises
            }
        )
    except Exception as e:
        logger.error(f"Error accessing database: {str(e)}")
        return templates.TemplateResponse(
            "map.html",
            {
                "request": request,
                "user": user,
                "enterprises": []
            }
        )

@router.get("/test-map")
async def test_map():
    return {"message": "Map router is working"} 