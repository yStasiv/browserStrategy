from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from .db_base import Base
from datetime import datetime


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

    user_tasks = relationship("UserTask", back_populates="user")

    achievements = relationship("UserAchievement", back_populates="user")


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
    scenario_id = Column(Integer, ForeignKey("quest_scenarios.id"))
    title = Column(String)
    description = Column(String)
    level_required = Column(Integer, default=1)
    order_in_scenario = Column(Integer, default=0)
    reward_gold = Column(Integer, default=0)
    reward_wood = Column(Integer, default=0)
    reward_stone = Column(Integer, default=0)
    reward_exp = Column(Integer, default=0)

    user_tasks = relationship("UserTask", back_populates="task")
    scenario = relationship("QuestScenario", back_populates="tasks")

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
    area = Column(Integer, default=100)  # Площа підприємства в умовних одиницях
    last_production_time = Column(DateTime, nullable=True)  # Час останнього виробництва
    workers_count = Column(Integer, default=0)  # Кількість працівників
    max_workers = Column(Integer, default=10)  # Максимальна кількість працівників
    max_storage = Column(Integer, default=666)  # Максимальна кількість ресурсу на складі
    salary = Column(Integer, default=30)  # Зарплата за годину
    item_price = Column(Integer, default=11)  # Ціна за одиницю ресурсу
    balance = Column(Integer, default=1000)  # Додаємо поле балансу
    storage_multiplier = Column(Integer, default=40)  # Коефіцієнт для розміру складу
    production_type = Column(String, default="factory")  # factory або mine

class QuestScenario(Base):
    __tablename__ = "quest_scenarios"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)  # Назва сценарію
    description = Column(String)  # Опис сценарію
    min_level = Column(Integer, default=1)  # Мінімальний рівень для доступу
    is_active = Column(Boolean, default=True)  # Чи активний сценарій
    tasks = relationship("Task", back_populates="scenario")

class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    icon_url = Column(String, nullable=True)

class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    achievement_id = Column(Integer, ForeignKey("achievements.id"))
    obtained_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement")