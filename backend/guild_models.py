from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, ForeignKey, ForeignKeyConstraint,
    Integer, Numeric, String, UniqueConstraint,
)

from .db_base import Base


class GuildProgress(Base):
    __tablename__ = "guild_progress"

    player_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    level = Column(Integer, nullable=False)
    xp = Column(Integer, nullable=False)
    next_xp = Column(Integer, nullable=False)
    claimed_count = Column(Integer, nullable=False)


class GuildQuestTemplate(Base):
    __tablename__ = "guild_quest_templates"

    key = Column(String(64), primary_key=True)
    title = Column(String, nullable=False)
    category = Column(String(32), nullable=False)
    resource = Column(String(32), nullable=False)
    difficulty = Column(String(32), nullable=False)
    min_level = Column(Integer, nullable=False)
    required = Column(Integer, nullable=False)
    gold = Column(Integer, nullable=False)
    wood = Column(Integer, nullable=False)
    stone = Column(Integer, nullable=False)
    xp = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False)


class GuildQuest(Base):
    __tablename__ = "guild_quest_instances"
    __table_args__ = (
        UniqueConstraint("player_id", "id"),
        CheckConstraint("progress >= 0 AND progress <= required AND required > 0"),
        CheckConstraint("status IN ('available', 'in_progress', 'completed', 'reward_claimed', 'replaced')"),
    )

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("guild_progress.player_id"), nullable=False)
    template_key = Column(String(64), ForeignKey("guild_quest_templates.key"), nullable=False)
    generation_level = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String(32), nullable=False)
    resource = Column(String(32), nullable=False)
    difficulty = Column(String(32), nullable=False)
    required = Column(Integer, nullable=False)
    progress = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    gold = Column(Integer, nullable=False)
    wood = Column(Integer, nullable=False)
    stone = Column(Integer, nullable=False)
    xp = Column(Integer, nullable=False)


class GuildQuestSlot(Base):
    __tablename__ = "guild_quest_slots"
    __table_args__ = (
        CheckConstraint("number BETWEEN 1 AND 5"),
        ForeignKeyConstraint(
            ["player_id", "quest_id"], ["guild_quest_instances.player_id", "guild_quest_instances.id"]
        ),
        UniqueConstraint("quest_id"),
    )

    player_id = Column(Integer, ForeignKey("guild_progress.player_id"), primary_key=True)
    number = Column(Integer, primary_key=True)
    quest_id = Column(Integer, nullable=False)


class GuildDailyReplacement(Base):
    __tablename__ = "guild_daily_replacements"
    __table_args__ = (CheckConstraint("used BETWEEN 0 AND 3"),)

    player_id = Column(Integer, ForeignKey("guild_progress.player_id"), primary_key=True)
    utc_date = Column(Date, primary_key=True)
    used = Column(Integer, nullable=False)


class GuildEvent(Base):
    __tablename__ = "guild_processed_events"

    player_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    event_type = Column(String(32), primary_key=True)
    source_id = Column(String(64), primary_key=True)


class ActivityGuildProgress(Base):
    __tablename__ = "activity_guild_progress"

    player_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    guild = Column(String(32), primary_key=True)
    points = Column(Numeric(16, 3), nullable=False)
