from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend import db_base
from backend.auth import session_player
from backend.config import SYSTEM_PLAYER_ID, SYSTEM_PLAYER_USERNAME
from backend.models import Enterprise, User
from backend.routers.auth import AuthRotes
from backend.scripts.set_system_player_password import set_password


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'world.db'}")

    @sa.event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "20261118_02")
    yield engine
    engine.dispose()


def test_migration_preserves_admin_and_assigns_owners(legacy_db):
    with legacy_db.begin() as connection:
        metadata = sa.MetaData()
        metadata.reflect(connection)
        rows = {
            "users": [
                dict(id=1, username="1", fraction="Admin", password="existing-hash",
                     is_active=True, session_id="old-session", gold=70, map_sector="Castle"),
                dict(id=4, username="player", is_active=True, map_sector="Castle"),
            ],
            "enterprises": [dict(id=1, sector="Forest", resource_stored=30, balance=85)],
            "items": [dict(id=8, owner_id=1)],
            "guild_progress": [dict(player_id=1, level=2, xp=12, next_xp=150, claimed_count=3)],
            "guild_quest_instances": [
                dict(id=10, player_id=1, template_key="wood_supply", generation_level=2,
                     title="Test", description="Test quest", category="collection", resource="wood",
                     difficulty="Easy", required=5, progress=2, status="in_progress",
                     gold=12, wood=0, stone=0, xp=30),
            ],
            "guild_quest_slots": [dict(player_id=1, number=1, quest_id=10)],
        }
        for table, values in rows.items():
            for row in values:
                connection.execute(metadata.tables[table].insert().values(**row))

    command.upgrade(Config("alembic.ini"), "head")

    with Session(legacy_db) as db:
        system = db.get(User, SYSTEM_PLAYER_ID)
        admin = db.scalar(sa.select(User).where(User.is_admin.is_(True)))
        assert admin.id == 5
        assert (admin.username, admin.password, admin.gold, admin.session_id) == ("1", "existing-hash", 70, None)
        assert (system.is_system, system.is_active, system.is_admin, system.password) == (True, True, False, None)
        assert db.execute(sa.text("SELECT owner_id FROM items WHERE id=8")).scalar_one() == admin.id
        assert db.execute(sa.text("SELECT player_id, quest_id FROM guild_quest_slots")).one() == (admin.id, 10)
        assert db.execute(sa.text("SELECT player_id, progress FROM guild_quest_instances")).one() == (admin.id, 2)
        enterprise = db.get(Enterprise, 1)
        assert (enterprise.owner_id, enterprise.sector, enterprise.resource_stored, enterprise.balance) == (
            SYSTEM_PLAYER_ID, "Forest", 30, 85
        )
        new_enterprise = Enterprise(name="New enterprise")
        db.add(new_enterprise)
        db.flush()
        assert new_enterprise.owner_id == SYSTEM_PLAYER_ID
        assert db.execute(sa.text("PRAGMA foreign_key_check")).all() == []
        assert system.username == SYSTEM_PLAYER_USERNAME
        assert (system.fraction, system.pending_attribute_points, system.stamina) == ("elfe", 1, 0)
        request = Request({"type": "http", "headers": []})
        with pytest.raises(HTTPException) as missing_password:
            AuthRotes.login(request, SYSTEM_PLAYER_USERNAME, "test-password", db)
        assert missing_password.value.status_code == 401
        set_password(db, "test-password")
        response = AuthRotes.login(request, SYSTEM_PLAYER_USERNAME, "test-password", db)
        assert response.status_code == 303
        db.refresh(system)
        system_session = system.session_id
        assert session_player(SimpleNamespace(cookies={"session_id": system_session}), db) is system
        set_password(db, "rotated-password")
        assert session_player(SimpleNamespace(cookies={"session_id": system_session}), db) is None
        admin.session_id = "admin-session"
        db.flush()
        assert session_player(SimpleNamespace(cookies={"username": "1"}), db) is None
        assert session_player(SimpleNamespace(cookies={"session_id": "admin-session"}), db) is admin


def test_migration_stops_for_unknown_player_one(legacy_db):
    with legacy_db.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id, username, gold) VALUES (1, 'existing', 42)"))

    with pytest.raises(RuntimeError, match="unrecognized account"):
        command.upgrade(Config("alembic.ini"), "head")

    with legacy_db.connect() as connection:
        assert connection.execute(sa.text("SELECT username, gold FROM users WHERE id=1")).one() == ("existing", 42)
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20261118_02"
        assert "is_system" not in {column["name"] for column in sa.inspect(connection).get_columns("users")}
