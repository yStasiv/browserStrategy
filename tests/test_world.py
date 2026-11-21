from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import db_base
from backend.models import User
from backend.services import world
from backend.world_models import PlayerTravel, WorldSector


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'world.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    factory = sessionmaker(engine)
    with factory.begin() as db:
        db.add_all([User(id=10, username="traveler"), User(id=20, username="neighbor")])
    yield factory
    engine.dispose()


def test_travel_persistence_timing_and_isolation(sessions, monkeypatch):
    now = datetime(2026, 11, 18, 12)
    monkeypatch.setattr(world, "utc_now", lambda: now)

    with sessions.begin() as db:
        player = db.get(User, 10)
        journey, started = world.start_travel(db, player, "Mountain")
        assert journey.arrives_at - started == timedelta(seconds=2)
        assert player.map_sector == "Castle"

    now += timedelta(milliseconds=1999)
    with sessions.begin() as db:
        player = db.get(User, 10)
        journey, _ = world.resolve_location(db, player)
        assert journey.destination == "Mountain"
        assert player.map_sector == "Castle"
        with pytest.raises(HTTPException, match="Подорож уже триває"):
            world.start_travel(db, player, "Forest")

    now += timedelta(milliseconds=1)
    with sessions.begin() as db:
        player = db.get(User, 10)
        journey, _ = world.resolve_location(db, player)
        assert journey is None
        assert player.map_sector == "Mountain"
        with pytest.raises(HTTPException, match="немає прямого"):
            world.start_travel(db, player, "Forest")

        other = db.get(User, 20)
        journey, started = world.start_travel(db, other, "Forest")
        assert journey.arrives_at - started == timedelta(seconds=4)
        assert other.map_sector == "Castle"

    with sessions() as db:
        assert db.get(User, 10).map_sector == "Mountain"
        assert db.get(PlayerTravel, 10) is None
        assert db.get(PlayerTravel, 20).destination == "Forest"


def test_new_sector_is_global_and_connection_can_be_one_way(sessions, monkeypatch):
    now = datetime(2026, 11, 18, 12)
    monkeypatch.setattr(world, "utc_now", lambda: now)

    with sessions.begin() as db:
        db.add(WorldSector(key="Ruins", name="Руїни", unlocked=False, sort_order=3))
        db.flush()
        world.set_connection(db, "Castle", "Ruins", 6, bidirectional=False)

    with sessions.begin() as db:
        player = db.get(User, 10)
        with pytest.raises(HTTPException, match="заблокований"):
            world.start_travel(db, player, "Ruins")
        state = world.map_state(db, player, None, now)
        assert state["sectors"][-1]["key"] == "Ruins"
        assert state["sectors"][-1]["duration_seconds"] == 6
        world.unlock_sector(db, "Ruins")

    with sessions.begin() as db:
        for player_id in (10, 20):
            world.start_travel(db, db.get(User, player_id), "Ruins")

    now += timedelta(seconds=6)
    with sessions.begin() as db:
        player = db.get(User, 10)
        with pytest.raises(HTTPException, match="немає прямого"):
            world.start_travel(db, player, "Castle")
        assert player.map_sector == "Ruins"


def test_simultaneous_departures_allow_only_one_journey(sessions):
    barrier = Barrier(2)

    def depart(destination):
        try:
            with sessions.begin() as db:
                player = db.get(User, 10)
                barrier.wait(timeout=5)
                world.start_travel(db, player, destination)
        except HTTPException as error:
            assert error.status_code == 409
            return None
        return destination

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted = [value for value in pool.map(depart, ["Mountain", "Forest"]) if value]
    assert len(accepted) == 1
    with sessions() as db:
        assert db.get(PlayerTravel, 10).destination == accepted[0]
        assert db.get(PlayerTravel, 20) is None
