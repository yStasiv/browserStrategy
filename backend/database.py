from typing import Any, Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .auth import session_player
from .db_base import SessionLocal


def get_db() -> Generator[Any, Any, Any]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from .db_base import Base, engine

    from sqlalchemy import inspect

    if not inspect(engine).has_table("world_sectors"):
        return
    legacy_tables = [
        table for table in Base.metadata.sorted_tables
        if not table.name.startswith(("guild_", "world_"))
        and table.name not in {
            "reward_transactions", "player_travel", "player_resource_balances", "activity_guild_progress",
            "castle_buildings", "enterprise_shifts", "enterprise_events", "enterprise_daily_reports", "repair_jobs", "gameplay_events",
            "player_moderation_events", "news", "news_acknowledgments",
            "global_events", "event_constructions", "construction_contributions", "event_rewards", "global_event_audit",
        }
    ]
    Base.metadata.create_all(bind=engine, tables=legacy_tables)


def get_current_user(request: Request, db: Session = Depends(get_db)):
    return session_player(request, db)
