from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend import database
from backend.models import User
from backend.services.world import utc_now

router = APIRouter()
ONLINE_WINDOW = timedelta(seconds=120)


@router.post("/api/presence")
def update_presence(request: Request, db: Session = Depends(database.get_db)):
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401)
    now = utc_now()
    result = db.execute(update(User)
                        .where(User.session_id == session_id, User.is_active.is_(True))
                        .values(last_seen_at=now))
    if not result.rowcount:
        raise HTTPException(status_code=401)
    count = db.scalar(select(func.count()).select_from(User).where(
        User.is_active.is_(True),
        User.session_id.is_not(None),
        User.last_seen_at > now - ONLINE_WINDOW,
    ))
    db.commit()
    return {"online": count}
