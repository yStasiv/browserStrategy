from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend import database
from backend.auth import session_player
from backend.models import User
from backend.services.world import utc_now

router = APIRouter()
ONLINE_WINDOW = timedelta(seconds=120)


@router.post("/api/presence")
def update_presence(request: Request, db: Session = Depends(database.get_db)):
    player = session_player(request, db)
    if player is None:
        raise HTTPException(status_code=401)
    now = utc_now()
    result = db.execute(update(User)
                        .where(User.id == player.id, User.session_id == player.session_id,
                               User.is_active.is_(True), User.ban_reason.is_(None),
                               User.nickname_reset_from.is_(None))
                        .values(last_seen_at=now))
    if not result.rowcount:
        db.expire_all()
        session_player(request, db)
        raise HTTPException(status_code=401)
    count = db.scalar(select(func.count()).select_from(User).where(
        User.is_active.is_(True),
        User.session_id.is_not(None),
        User.ban_reason.is_(None),
        User.nickname_reset_from.is_(None),
        User.last_seen_at > now - ONLINE_WINDOW,
    ))
    db.commit()
    return {"online": count}
