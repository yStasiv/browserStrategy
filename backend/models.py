from sqlalchemy import Boolean, Column, Integer, String, ForeignKey
from .database import Base
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    avatar_url = Column(String, nullable=True) # user img path
    fraction = Column(String, default="Elfe")

    pending_attribute_points =  Column(Integer, default=1)
    strength = Column(Integer, default=0)
    defense = Column(Integer, default=0)
    initiative = Column(Integer, default=0)

    experience = Column(Integer, default=1)

    level = Column(Integer, default=1)  
    gold = Column(Integer, default=0) 
    wood = Column(Integer, default=0)  
    stone = Column(Integer, default=0) 
    session_id = Column(String, unique=True, nullable=True)

    units = relationship("UserUnit", back_populates="user")

    tasks = relationship("Task", back_populates="user")
    user_tasks = relationship("UserTask", back_populates="user")


class UnitType(Base):
    __tablename__ = "unit_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    fraction = Column(String)
    level_required = Column(Integer)
    max_quantity = Column(Integer)
    icon_url = Column(String)

class UserUnit(Base):
    __tablename__ = "user_units"

    id = Column(Integer, primary_key=True, index=True)  # TODO: could be removed?
    user_id = Column(Integer, ForeignKey("users.id"))
    unit_type_id = Column(Integer, ForeignKey("unit_types.id"))
    quantity = Column(Integer, default=0)

    user = relationship("User", back_populates="units")
    unit_type = relationship("UnitType")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    is_completed = Column(Boolean, default=False)
    reward_gold = Column(Integer, default=0)
    reward_wood = Column(Integer, default=0) 
    reward_stone = Column(Integer, default=0) 
    reward_exp = Column(Integer, default=0) 
    # level_required = Column(Integer, ForeignKey("users.level"), default=1)
    level_required = Column(Integer, ForeignKey("users.id"), default=1)  # TODO remove this fields? $1


    user = relationship("User", back_populates="tasks")   # TODO remove this fields? $1
    user_tasks = relationship("UserTask", back_populates="task")

class UserTask(Base): 
    __tablename__ = "user_tasks" 
    
    id = Column(Integer, primary_key=True, index=True) 
    user_id = Column(Integer, ForeignKey("users.id")) 
    task_id = Column(Integer, ForeignKey("tasks.id")) 
    is_completed = Column(Boolean, default=False) 

    user = relationship("User", back_populates="user_tasks") 
    task = relationship("Task", back_populates="user_tasks")