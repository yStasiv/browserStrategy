from datetime import datetime
from enum import Enum

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String)
from sqlalchemy.orm import relationship

from .db_base import Base

# USER

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    avatar_url = Column(String, nullable=True)  # user img path
    fraction = Column(String, default="Elfe")

    pending_attribute_points = Column(Integer, default=1)
    # Основні характеристики
    stamina = Column(Integer, default=0)  # Здоров'я
    energy = Column(Integer, default=0)  # Енергія
    agility = Column(Integer, default=0)  # Спритність
    mind = Column(Integer, default=0)  # Розум

    # Додаткові характеристики
    melee_attack = Column(Integer, default=0)  # Атака в ближньому бою
    ranged_attack = Column(Integer, default=0)  # Атака в дальньому бою
    magic_power = Column(Integer, default=0)  # Магічний потенціал
    physical_defense = Column(Integer, default=0)  # Захист від фізичних атак
    magic_resistance = Column(Integer, default=0)  # Стійкість до магії

    # Бонуси до шкоди
    bonus_melee_damage = Column(Integer, default=0)
    bonus_ranged_damage = Column(Integer, default=0)
    bonus_magic_damage = Column(Integer, default=0)

    # Бонуси до захисту
    bonus_melee_defense = Column(Integer, default=0)
    bonus_ranged_defense = Column(Integer, default=0)
    bonus_magic_defense = Column(Integer, default=0)

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

    inventory_items = relationship("Item", back_populates="owner")
    equipped_items = relationship("EquippedItems", back_populates="user", uselist=False)

    battles = relationship("BattleState", back_populates="user")

# INVENTORY - ARTEFACTS - EQUIPMENT

class ItemType(str, Enum):
    WEAPON_1H = "one_handed_weapon"
    WEAPON_2H = "two_handed_weapon"
    JEWELRY = "jewelry"
    HELMET = "helmet"
    ARMOR = "armor"
    BOOTS = "boots"
    BACK = "back"


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    description = Column(String)
    item_type = Column(String)  # Використовуємо значення з ItemType
    image_url = Column(String)
    stats = Column(JSON)  # Зберігаємо характеристики предмета у JSON
    is_equipped = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    durability = Column(Integer)  # Поточна міцність
    max_durability = Column(Integer)  # Максимальна міцність

    owner = relationship("User", back_populates="inventory_items")


class EquippedItems(Base):
    __tablename__ = "equipped_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    helmet_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    armor_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    boots_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    right_hand_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    left_hand_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    back_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    jewelry_1_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    jewelry_2_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    jewelry_3_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    jewelry_4_id = Column(Integer, ForeignKey("items.id"), nullable=True)

    user = relationship("User", back_populates="equipped_items")
    helmet = relationship("Item", foreign_keys=[helmet_id])
    armor = relationship("Item", foreign_keys=[armor_id])
    boots = relationship("Item", foreign_keys=[boots_id])
    right_hand = relationship("Item", foreign_keys=[right_hand_id])
    left_hand = relationship("Item", foreign_keys=[left_hand_id])
    back = relationship("Item", foreign_keys=[back_id])
    jewelry_1 = relationship("Item", foreign_keys=[jewelry_1_id])
    jewelry_2 = relationship("Item", foreign_keys=[jewelry_2_id])
    jewelry_3 = relationship("Item", foreign_keys=[jewelry_3_id])
    jewelry_4 = relationship("Item", foreign_keys=[jewelry_4_id])

class ShopItem(Base):
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True)
    item_template_id = Column(Integer, ForeignKey("items.id"))
    price = Column(Integer, nullable=False)
    quantity = Column(Integer, default=-1)  # -1 означає необмежену кількість
    level_required = Column(Integer, default=1)

    item_template = relationship("Item")


# ARMY

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

# BATTLES

class BattleState(Base):
    __tablename__ = "battle_state"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    enemy_id = Column(Integer, ForeignKey("enemies.id"))
    player_position = Column(JSON)  # Позиція героя на полі бою
    enemy_position = Column(JSON)  # Позиція ворога на полі бою
    player_hp = Column(Integer, default=100)
    enemy_hp = Column(Integer, default=100)
    turn = Column(Integer, default=1)
    player_moves = Column(Integer, default=3)  # Кількість ходів руху за хід
    enemy_moves = Column(Integer, default=2)  # Кількість ходів руху за хід
    battle_ended = Column(Boolean, default=False)
    winner = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Зв'язки
    user = relationship("User", back_populates="battles")
    enemy = relationship("Enemy", back_populates="battles")
    battle_logs = relationship("BattleLog", back_populates="battle", cascade="all, delete-orphan")

class BattleLog(Base):
    __tablename__ = "battle_logs"

    id = Column(Integer, primary_key=True, index=True)
    battle_id = Column(Integer, ForeignKey("battle_state.id"))
    turn = Column(Integer)
    player_action = Column(String)  # move, attack, defend, special_attack
    player_hp = Column(Integer)
    enemy_hp = Column(Integer)
    player_damage = Column(Integer, default=0)
    enemy_damage = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Зв'язки
    battle = relationship("BattleState", back_populates="battle_logs")

class Enemy(Base):
    __tablename__ = "enemies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    level = Column(Integer, default=1)
    image_url = Column(String, default="../static/images/enemy.svg")
    
    # Основні характеристики
    hp = Column(Integer, default=100)
    melee_attack = Column(Integer, default=10)
    physical_defense = Column(Integer, default=5)
    magic_power = Column(Integer, default=0)
    magic_resistance = Column(Integer, default=0)
    
    # Додаткові характеристики
    ranged_attack = Column(Integer, default=0)
    agility = Column(Integer, default=0)
    mind = Column(Integer, default=0)
    
    # Бонуси до шкоди
    bonus_melee_damage = Column(Integer, default=0)
    bonus_ranged_damage = Column(Integer, default=0)
    bonus_magic_damage = Column(Integer, default=0)
    
    # Бонуси до захисту
    bonus_melee_defense = Column(Integer, default=0)
    bonus_ranged_defense = Column(Integer, default=0)
    bonus_magic_defense = Column(Integer, default=0)
    
    # Нагороди за перемогу
    exp_reward = Column(Integer, default=10)
    gold_reward = Column(Integer, default=5)
    
    # Зв'язки
    battles = relationship("BattleState", back_populates="enemy")

# TASKS - QUESTS

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

# ENTERPRISES - STORES - BUILDINGS

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
    max_storage = Column(
        Integer, default=666
    )  # Максимальна кількість ресурсу на складі
    salary = Column(Integer, default=30)  # Зарплата за годину
    item_price = Column(Integer, default=11)  # Ціна за одиницю ресурсу
    balance = Column(Integer, default=1000)  # Додаємо поле балансу
    storage_multiplier = Column(Integer, default=40)  # Коефіцієнт для розміру складу
    production_type = Column(String, default="factory")  # factory або mine





