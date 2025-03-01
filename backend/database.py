from typing import Any, Generator
from sqlalchemy.orm import Session
from fastapi import Request, Depends
from .db_base import SessionLocal
from . import models

def get_db() -> Generator[Any, Any, Any]:
    db = SessionLocal()
    try:
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
    