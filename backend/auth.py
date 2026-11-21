from sqlalchemy.orm import Session

from backend import models


def playable_users(db: Session):
    return db.query(models.User).filter(models.User.is_active.is_(True))


def session_player(request, db: Session):
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    return playable_users(db).filter(models.User.session_id == session_id).first()


async def get_current_user(request, db: Session):
    return session_player(request, db)
