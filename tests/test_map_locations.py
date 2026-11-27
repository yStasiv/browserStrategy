import asyncio
import json
import struct
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, select, text

from backend import database, db_base
from backend.models import Enterprise, User
from backend.routers import admin, enterprise, map as player_map
from backend.services import map_config
from backend.world_models import PlayerTravel, WorldSector
from test_guild import asgi_request, sessions


def test_world_geography_and_every_progression_stage():
    data = map_config.config()
    total = data["map"]["total_locations"]
    assert len(data["locations"]) == len({row["key"] for row in data["locations"]}) == total
    picture = Path("frontend" + data["map"]["image"]).read_bytes()
    assert struct.unpack(">II", picture[16:24]) == (data["map"]["width"], data["map"]["height"])
    playable = map_config.polygon_area(data["map"]["playable_area"]["points"])
    assert abs(sum(map_config.polygon_area(row["geometry"]["points"]) for row in data["locations"]) - playable) < 1e-7
    reached = set()
    for row in sorted(data["locations"], key=lambda row: row["unlock_order"]):
        points = row["geometry"]["points"]
        assert len(points) > 4
        assert map_config.polygon_area(points) > 0
        assert all(0 <= coordinate <= 1 for point in points for coordinate in point)
        assert map_config.contains(points, **row["marker"])
        if reached:
            assert any(link["location_id"] in reached for link in row["connections"])
        reached.add(row["id"])
        for key, seconds in map_config.routes_from(row["key"]).items():
            assert map_config.routes_from(key)[row["key"]] == seconds
            assert isinstance(seconds, int) and seconds > 0
    port = next(row for row in data["locations"] if row["features"]["port"])
    assert len(reached) == total and (port["id"], port["unlock_order"]) == (33, total)
    assert port["connections"]


def test_unlock_visibility_permissions_persistence_and_travel(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    for router in (admin, player_map, enterprise):
        app.include_router(router.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, account="reader", **kwargs):
        return asyncio.run(asgi_request(app, method, path, f"session_id={account}-session", **kwargs))

    with sessions.begin() as db:
        db.get(User, 10).is_admin = True
        db.add(Enterprise(id=99, name="Замкнена копальня", sector="Forest", resource_type="basalt_bone"))

    status, body = call("GET", "/api/world")
    state = json.loads(body)
    assert status == 200 and state["fog_of_war"]["enabled"]
    assert [row["key"] for row in state["sectors"]] == ["Castle"]
    assert "Золотолісся" not in body.decode()
    assert call("POST", "/move-to-sector", payload={"sector": "Forest"})[0] == 403
    assert call("GET", "/enterprise/99")[0] == 403
    with sessions.begin() as db:
        db.get(User, 2).map_sector = "Forest"
    assert call("GET", "/enterprise/99", "other")[0] == 403
    assert call("POST", "/move-to-sector", "other", payload={"sector": "Castle"})[0] == 403
    with sessions.begin() as db:
        db.get(User, 2).map_sector = "Castle"
    assert call("GET", "/admin/map/editor", "other")[0] == 403
    assert call("POST", "/admin/map/unlock-next", "other")[0] == 403
    assert call("GET", "/admin/map/editor")[0] == 200
    assert call("POST", "/admin/map/locations/33/unlock")[0] == 409

    def open_next():
        status, body = call("POST", "/admin/map/unlock-next")
        assert status == 200
        result = json.loads(body)
        assert result["changed"]
        return result["location_id"]

    assert open_next() == 9
    assert open_next() == 3
    assert json.loads(call("POST", "/admin/map/locations/3/unlock")[1])["changed"] is False
    state = json.loads(call("GET", "/api/world", "other")[1])
    assert {row["key"]: row["duration_seconds"] for row in state["sectors"]} == {
        "Castle": None, "Mountain": 2, "Forest": 4,
    }
    with sessions.begin() as db:
        assert db.get(WorldSector, "Forest").unlocked_by == 10
        assert db.get(WorldSector, "Forest").unlocked_at is not None
        assert len(list(db.scalars(select(WorldSector).where(WorldSector.location_id == 3)))) == 1
        db.get(User, 2).map_sector = "Mountain"
    assert call("POST", "/move-to-sector", "other", payload={"sector": "Forest"})[0] == 409
    assert call("POST", "/move-to-sector", "other", payload={"sector": "Castle"})[0] == 200
    total = map_config.config()["map"]["total_locations"]
    remaining = [open_next() for _ in range(total - len(state["sectors"]))]
    assert remaining[-1] == 33
    state = json.loads(call("GET", "/api/world")[1])
    assert len(state["sectors"]) == total and not state["fog_of_war"]["enabled"]


def test_map_migration_keeps_existing_players_enterprises_and_journeys(tmp_path, monkeypatch):
    path = tmp_path / "established.db"
    engine = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "20261125_28")
    now = datetime(2026, 11, 26, 13)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users (id, username, map_sector, gold) VALUES (55, 'traveler', 'Forest', 712)"))
        db.execute(text("INSERT INTO enterprises (id, sector, name) VALUES (77, 'Mountain', 'Mine')"))
        db.execute(text("INSERT INTO player_travel VALUES (55, 'Forest', 'Castle', :start, :end)"),
                   {"start": now, "end": now + timedelta(seconds=4)})
    command.upgrade(Config("alembic.ini"), "20261126_29")
    with engine.begin() as db:
        db.execute(text("UPDATE world_sectors SET map_x=83, map_y=50 WHERE key='Forest'"))
        db.execute(text("INSERT INTO world_sector_connections VALUES ('Forest', 'royal_port', 4, TRUE)"))
    for _ in range(2):
        command.upgrade(Config("alembic.ini"), "head")
    engine.dispose()
    reopened = create_engine(f"sqlite:///{path}")
    with reopened.connect() as db:
        assert db.execute(select(User.map_sector, User.gold).where(User.id == 55)).one() == ("Forest", 712)
        assert db.scalar(select(Enterprise.sector).where(Enterprise.id == 77)) == "Mountain"
        assert db.execute(select(PlayerTravel.origin, PlayerTravel.destination)).one() == ("Forest", "Castle")
        assert set(db.scalars(select(WorldSector.key).where(WorldSector.unlocked.is_(True)))) == {"Castle", "Mountain", "Forest"}
        assert db.execute(select(WorldSector.map_x, WorldSector.map_y).where(WorldSector.key == "Forest")).one() == map_config.marker_position("Forest")
        assert not db.execute(text("SELECT 1 FROM world_sector_connections WHERE origin='Forest' AND destination='royal_port'")).first()
        assert not db.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    reopened.dispose()
