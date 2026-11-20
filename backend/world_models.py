from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String

from .db_base import Base


class WorldSector(Base):
    __tablename__ = "world_sectors"
    __table_args__ = (
        CheckConstraint(
            "(map_x IS NULL AND map_y IS NULL) OR "
            "(map_x IS NOT NULL AND map_y IS NOT NULL AND map_x BETWEEN 0 AND 100 AND map_y BETWEEN 0 AND 100)",
            name="ck_world_sector_map_position",
        ),
    )

    key = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    unlocked = Column(Boolean, nullable=False)
    sort_order = Column(Integer, nullable=False)
    map_x = Column(Integer)
    map_y = Column(Integer)


class SectorConnection(Base):
    __tablename__ = "world_sector_connections"
    __table_args__ = (
        CheckConstraint("origin != destination", name="ck_world_distinct_sectors"),
        CheckConstraint("duration_seconds > 0", name="ck_world_positive_duration"),
    )

    origin = Column(String, ForeignKey("world_sectors.key"), primary_key=True)
    destination = Column(String, ForeignKey("world_sectors.key"), primary_key=True)
    duration_seconds = Column(Integer, nullable=False)


class PlayerTravel(Base):
    __tablename__ = "player_travel"
    __table_args__ = (
        CheckConstraint("origin != destination", name="ck_travel_distinct_sectors"),
        CheckConstraint("arrives_at > started_at", name="ck_travel_positive_duration"),
    )

    player_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    origin = Column(String, ForeignKey("world_sectors.key"), nullable=False)
    destination = Column(String, ForeignKey("world_sectors.key"), nullable=False)
    started_at = Column(DateTime, nullable=False)
    arrives_at = Column(DateTime, nullable=False)
