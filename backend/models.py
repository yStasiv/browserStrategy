from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from .db_base import Base


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

    map_sector = Column(String, default="Castle")  # Сектор карти
    map_x = Column(Integer, default=0)  # Координата X на карті
    map_y = Column(Integer, default=0)  # Координата Y на карті

    workplace = Column(String, nullable=True)  # Назва підприємства, де працює
    last_salary_time = Column(DateTime, nullable=True)  # Час останньої виплати
    last_quit_time = Column(DateTime, nullable=True)  # Час останнього звільнення

    # Додаємо нові поля для відстеження часу роботи
    daily_work_minutes = Column(Integer, default=0)  # Хвилини роботи за день
    last_work_day = Column(DateTime, nullable=True)  # Останній робочий день

    work_start_time = Column(DateTime, nullable=True)  # Час початку роботи

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

class Enterprise(Base):
    __tablename__ = "enterprises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)  # Назва підприємства (sawmill, mine, etc.)
    sector = Column(String, default="Castle")  # Додаємо поле для сектора
    resource_type = Column(String)  # Тип ресурсу (wood, stone, etc.)
    resource_stored = Column(Integer, default=0)  # Кількість ресурсу на складі
    last_production_time = Column(DateTime, nullable=True)  # Час останнього виробництва
    workers_count = Column(Integer, default=0)  # Кількість працівників
    max_workers = Column(Integer, default=10)  # Максимальна кількість працівників
    max_storage = Column(Integer, default=666)  # Максимальна кількість ресурсу на складі
    salary = Column(Integer, default=3)  # Зарплата за хвилину
    item_price = Column(Integer, default=11)  # Ціна за одиницю ресурсу
    balance = Column(Integer, default=1000)  # Додаємо поле балансу