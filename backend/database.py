from typing import Any, Generator
from sqlalchemy.orm import Session
from fastapi import Request, Depends
from .db_base import SessionLocal
from . import models
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .init_test_data import init_test_data, init_test_admin

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
            is_active=True
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
            reward_exp=50
        )
        db.add(default_task)
        db.commit()

def get_db() -> Generator[Any, Any, Any]:
    db = SessionLocal()
    try:
        init_test_data(db)  # Ініціалізуємо тестові дані
        init_test_admin(db)  # Створюємо адміністратора
        # init_default_task(db)  # Ініціалізуємо початкове завдання при створенні сесії
        yield db
    finally:
        db.close()

def init_db():
    from .db_base import Base, engine
    Base.metadata.create_all(bind=engine)
    # if not os.path.exists("database.db"):  # Check if database already created
    #     print("Database not found. Creating database...")
    # Base.metadata.create_all(bind=engine)  # Create new one if not

def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.cookies.get("username")
    if username:
        return db.query(models.User).filter(models.User.username == username).first()
    return None
    