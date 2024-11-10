from sqlalchemy import Column, Integer, String
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)

    level = Column(Integer, default=1)  
    gold = Column(Integer, default=0) 
    wood = Column(Integer, default=0)  
    stone = Column(Integer, default=0) 
    session_id = Column(String, unique=True, nullable=True)  # Додано поле для session_id
