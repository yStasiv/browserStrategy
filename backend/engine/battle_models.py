"""Таблиці бою. Припущення: Base лежить у backend/db_base.py, таблиця користувачів називається "users".
Якщо в вас інакше — змініть імпорт Base та ForeignKey("users.id") нижче."""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        String, UniqueConstraint)

from ..db_base import Base


class Battle(Base):
    __tablename__ = "battles"

    id = Column(Integer, primary_key=True)
    mode = Column(String(8), nullable=False)               # pve | pvp
    level = Column(Integer, nullable=False, default=1)     # рівень, за яким визначено правила поля
    status = Column(String(16), nullable=False, default="active", index=True)  # active | finished
    version = Column(Integer, nullable=False, default=0)   # оптимістичне блокування
    state = Column(JSON, nullable=False)                   # BattleState.to_dict()
    winner_side = Column(Integer, nullable=True)           # None при нічиїй або поки бій іде
    rewarded = Column(Boolean, nullable=False, default=False)  # нагороди видано (захист від дубля)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class BattleParticipant(Base):
    __tablename__ = "battle_participants"
    __table_args__ = (UniqueConstraint("battle_id", "side"),)

    id = Column(Integer, primary_key=True)
    battle_id = Column(Integer, ForeignKey("battles.id"), nullable=False, index=True)
    side = Column(Integer, nullable=False)                          # 0 або 1
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # NULL = ШІ


class BattleAction(Base):
    """Лог усіх дій (людини і ШІ). За ним бій можна відтворити з нуля."""
    __tablename__ = "battle_actions"
    __table_args__ = (UniqueConstraint("battle_id", "seq"),)

    id = Column(Integer, primary_key=True)
    battle_id = Column(Integer, ForeignKey("battles.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    side = Column(Integer, nullable=False)
    action = Column(JSON, nullable=False)
    events = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ArmySlot(Base):
    """Армія персонажа: до 8 слотів."""
    __tablename__ = "army_slots"
    __table_args__ = (UniqueConstraint("user_id", "slot"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    slot = Column(Integer, nullable=False)
    unit_key = Column(String(32), nullable=False)
    count = Column(Integer, nullable=False)
