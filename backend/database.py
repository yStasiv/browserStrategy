import os
from typing import Any, Generator
from requests import Session
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'database', 'users.db')}"

# Налаштування SQLAlchemy
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator[Any, Any, Any]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Функція для створення таблиць, якщо вони ще не існують
def init_db():
    # Створення таблиць на основі моделей
    if not os.path.exists("database.db"):  # Перевірка чи існує база даних
        print("Database not found. Creating database...")
    Base.metadata.create_all(bind=engine)  # Створює таблиці, якщо вони ще не існують
    