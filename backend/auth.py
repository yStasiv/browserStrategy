from fastapi import Request
from sqlalchemy.orm import Session
from backend import models

async def get_current_user(request: Request, db: Session):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        return None
    return db.query(models.User).filter(models.User.session_id == user_session_id).first() 