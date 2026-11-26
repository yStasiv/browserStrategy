from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend import models


def playable_users(db: Session):
    return db.query(models.User).filter(models.User.is_active.is_(True))


def require_unblocked(player):
    if player is not None and player.ban_reason is not None:
        raise HTTPException(403, f"Гравець заблокований: {player.ban_reason}")


class NicknameResetRequired(HTTPException):
    def __init__(self):
        super().__init__(409, "Обери новий нікнейм, щоб продовжити гру.")


def session_player(request, db: Session, *, allow_nickname_reset=False):
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    player = playable_users(db).filter(models.User.session_id == session_id).first()
    require_unblocked(player)
    if player is not None and player.nickname_reset_from is not None and not allow_nickname_reset:
        raise NicknameResetRequired()
    return player


async def get_current_user(request, db: Session):
    return session_player(request, db)
