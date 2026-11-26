from uuid import uuid4

from sqlalchemy import or_

from backend.models import User

TEMPORARY_PREFIX = "Гравець-"


def username_match(username):
    return or_(User.username == username, User.nickname_reset_from == username)


def temporary_name(db, player_id):
    while True:
        name = f"{TEMPORARY_PREFIX}{player_id}-{uuid4().hex[:8]}"
        if not db.query(User.id).filter(username_match(name)).first():
            return name


def validation_error(db, name):
    if not name or len(name) > 50:
        return "Введи нікнейм довжиною від 1 до 50 символів."
    if name.casefold().startswith(TEMPORARY_PREFIX.casefold()):
        return "Цей префікс зарезервовано для тимчасових нікнеймів."
    if db.query(User.id).filter(username_match(name)).first():
        return "Цей нікнейм уже зайнято."
    return None
