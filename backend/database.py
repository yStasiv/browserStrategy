from typing import Any, Generator

from fastapi import Depends, Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from . import models
from .db_base import SessionLocal
from .auth import session_player
from .init_test_data import init_test_data


def init_default_task(db: SessionLocal):
    """Створює початкове завдання з ID=1, якщо воно ще не існує"""
    # Перевіряємо чи існує завдання з ID=1
    task = db.query(models.Task).filter(models.Task.id == 1).first()
    if not task:
        # Створюємо сценарій для завдання
        scenario = models.QuestScenario(
            id=1,
            title="Початкові завдання",
            description="Базові завдання для нових гравців",
            min_level=1,
            is_active=True,
        )
        db.add(scenario)
        db.flush()  # Щоб отримати ID сценарію

        # Створюємо початкове завдання
        default_task = models.Task(
            id=1,
            scenario_id=scenario.id,
            title="Перше завдання",
            description="Ознайомтесь з гільдією авантюристів",
            level_required=1,
            order_in_scenario=1,
            reward_exp=50,
        )
        db.add(default_task)
        db.commit()


def get_db() -> Generator[Any, Any, Any]:
    db = SessionLocal()
    try:
        init_test_data(db)  # Ініціалізуємо тестові дані
        # init_default_task(db)  # Ініціалізуємо початкове завдання при створенні сесії
        yield db
    finally:
        db.close()


def init_db():
    from .db_base import Base, engine

    from sqlalchemy import inspect

    if not inspect(engine).has_table("world_sectors"):
        return
    legacy_tables = [
        table for table in Base.metadata.sorted_tables
        if not table.name.startswith(("guild_", "world_"))
        and table.name not in {
            "reward_transactions", "player_travel", "player_resource_balances", "activity_guild_progress",
            "castle_buildings", "enterprise_shifts", "enterprise_events",
        }
    ]
    Base.metadata.create_all(bind=engine, tables=legacy_tables)


def get_current_user(request: Request, db: Session = Depends(get_db)):
    return session_player(request, db)
