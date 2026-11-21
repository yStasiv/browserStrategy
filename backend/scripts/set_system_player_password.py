from getpass import getpass
import sys

from sqlalchemy import update

from backend.config import SYSTEM_PLAYER_ID, SYSTEM_PLAYER_USERNAME
from backend.db_base import SessionLocal
from backend.models import User
from backend.utils import hash_password


def set_password(db, password: str):
    if not password or len(password.encode("utf-8")) > 72:
        raise ValueError("Введіть непорожній пароль довжиною до 72 байтів.")
    result = db.execute(
        update(User).where(
            User.id == SYSTEM_PLAYER_ID,
            User.username == SYSTEM_PLAYER_USERNAME,
            User.is_system.is_(True),
        ).values(password=hash_password(password), session_id=None)
    )
    if result.rowcount != 1:
        raise ValueError("Системного персонажа не знайдено. Перевірте БД та версію міграції.")


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Запустіть команду в інтерактивному терміналі.")
    password = getpass("Новий пароль для персонажа «володар лісу»: ")
    if password != getpass("Повторіть пароль: "):
        raise SystemExit("Паролі не збігаються.")
    try:
        with SessionLocal.begin() as db:
            set_password(db, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Пароль встановлено. Попередню сесію завершено.")


if __name__ == "__main__":
    main()
