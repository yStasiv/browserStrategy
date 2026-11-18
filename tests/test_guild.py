import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from urllib.parse import urlencode

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import database, db_base
from backend.guild_models import GuildQuest, GuildQuestTemplate
from backend.models import Enterprise, User
from backend.routers import adventure_guild, enterprise
from backend.services import guild


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'guild.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    factory = sessionmaker(engine, autoflush=False)
    with factory.begin() as db:
        db.add_all([
            User(id=1, username="reader", level=8, gold=100, session_id="reader-session"),
            User(id=2, username="other", gold=100, session_id="other-session"),
            Enterprise(id=1, name="Sawmill", resource_type="wood", resource_stored=10, item_price=2),
        ])
    yield factory
    engine.dispose()


def test_progress_rewards_and_snapshots(sessions):
    with sessions.begin() as db:
        guild.initialize(db, 1)
        guild.initialize(db, 2)
    with sessions.begin() as db:
        initial = guild.board(db, 1)
        assert initial["level"] == 1
        assert len(initial["quests"]) == 5
        frozen = initial["quests"][-1]
        guild.record_collection(db, 1, "small-purchase", "wood", 1)
    with sessions.begin() as db:
        guild.record_collection(db, 1, "small-purchase", "wood", 1)
        db.flush()
        assert all(q["progress"] <= 1 for q in guild.board(db, 1)["quests"])
        assert all(q["progress"] == 0 for q in guild.board(db, 2)["quests"])
        guild.record_collection(db, 1, "wood-purchase", "wood", 20)
        guild.record_collection(db, 1, "stone-purchase", "stone", 20)
    with sessions.begin() as db:
        completed = guild.board(db, 1)["quests"]
        assert all(q["status"] == "completed" for q in completed)
        with pytest.raises(guild.GuildError, match="Завершений"):
            guild.replace(db, 1, completed[0]["id"], True)
        for quest in completed[:-1]:
            guild.claim(db, 1, quest["id"])
            db.flush()
        after = guild.board(db, 1)
        assert after["level"] == 2
        assert after["next_xp"] == guild.xp_threshold(2)
        assert after["xp"] == sum(q["xp"] for q in completed[:-1]) - guild.xp_threshold(1)
        assert after["claimed_count"] == 4
        assert db.get(User, 1).gold == 100 + sum(q["gold"] for q in completed[:-1])
        assert db.get(User, 1).wood == sum(q["wood"] for q in completed[:-1])
        assert db.get(User, 1).stone == sum(q["stone"] for q in completed[:-1])
        assert db.get(User, 1).level == 8
        assert after["quests"][-1]["required"] == frozen["required"]
        assert after["quests"][-1]["gold"] == frozen["gold"]
        generated = db.get(GuildQuest, after["quests"][3]["id"])
        assert generated.generation_level == 2
        template = db.get(GuildQuestTemplate, generated.template_key)
        assert generated.required > template.required
        assert generated.xp > template.xp
        with pytest.raises(guild.GuildError) as duplicate:
            guild.claim(db, 1, completed[0]["id"])
        assert duplicate.value.status_code == 409
        with pytest.raises(guild.GuildError) as wrong_player:
            guild.claim(db, 2, completed[-1]["id"])
        assert wrong_player.value.status_code == 404


def test_replacements_and_utc_reset(sessions, monkeypatch):
    monkeypatch.setattr(guild, "utc_today", lambda: date(2026, 11, 18))
    with sessions.begin() as db:
        guild.initialize(db, 1)
        db.flush()
        guild.record_collection(db, 1, "partial", "wood", 1)
        db.flush()
        before = guild.board(db, 1)
        partial = next(q for q in before["quests"] if q["progress"])
        with pytest.raises(guild.GuildError, match="Підтвердьте"):
            guild.replace(db, 1, partial["id"], False)
        guild.replace(db, 1, partial["id"], True)
        db.flush()
        replacement = guild.board(db, 1)["quests"][partial["slot"] - 1]
        assert replacement["progress"] == 0
        old = db.get(GuildQuest, partial["id"])
        assert old.status == "replaced"
        assert old.template_key != db.get(GuildQuest, replacement["id"]).template_key
        for quest in [q for q in before["quests"] if q != partial][:2]:
            guild.replace(db, 1, quest["id"], True)
            db.flush()
        exhausted = guild.board(db, 1)
        assert exhausted["replacements_remaining"] == 0
        assert exhausted["replacement_reset_at"] == "2026-11-19T00:00:00+00:00"
        with pytest.raises(guild.GuildError, match="вичерпано"):
            guild.replace(db, 1, replacement["id"], False)
        monkeypatch.setattr(guild, "utc_today", lambda: date(2026, 11, 19))
        assert guild.board(db, 1)["replacements_remaining"] == 3
        guild.replace(db, 1, replacement["id"], False)
        assert guild.board(db, 1)["replacements_remaining"] == 2


@pytest.mark.parametrize("operation, successes", [("claim", 1), ("replace", 3)])
def test_concurrent_mutations(sessions, operation, successes):
    with sessions.begin() as db:
        guild.initialize(db, 1)
        db.flush()
        if operation == "claim":
            guild.record_collection(db, 1, "wood-win", "wood", 20)
            guild.record_collection(db, 1, "stone-win", "stone", 20)
            db.flush()
        quests = guild.board(db, 1)["quests"]

    barrier = Barrier(5)

    def attempt(quest):
        barrier.wait(timeout=5)
        try:
            with sessions.begin() as db:
                if operation == "claim":
                    guild.claim(db, 1, quest["id"])
                else:
                    guild.replace(db, 1, quest["id"], False)
        except guild.GuildError:
            return False
        return True

    inputs = [quests[0]] * 5 if operation == "claim" else quests
    with ThreadPoolExecutor(max_workers=5) as workers:
        assert sum(workers.map(attempt, inputs)) == successes
    with sessions() as db:
        result = guild.board(db, 1)
        assert len(result["quests"]) == 5
        if operation == "claim":
            assert result["claimed_count"] == 1
            assert db.get(User, 1).gold == 100 + quests[0]["gold"]
        else:
            assert result["replacements_remaining"] == 0


async def asgi_request(app, method, path, cookie, form=None):
    messages = []
    headers = [(b"cookie", cookie.encode())]
    data = b""
    if form:
        data = urlencode(form).encode()
        headers.append((b"content-type", b"application/x-www-form-urlencoded"))

    async def receive():
        return {"type": "http.request", "body": data}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "method": method, "path": path, "query_string": b"",
        "headers": headers, "scheme": "http", "server": ("testserver", 80),
    }, receive, send)
    return messages[0]["status"], messages[-1]["body"]


def test_purchase_endpoint_and_guild_auth(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(adventure_guild.router)
    app.include_router(enterprise.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, form=None, cookie="session_id=reader-session"):
        return asyncio.run(asgi_request(app, method, path, cookie, form))

    assert call("GET", "/api/guild", cookie="username=reader")[0] == 401
    status, page = call("GET", "/guild")
    assert status == 200
    assert 'id="guild-quests"' in page.decode()
    assert call("POST", "/api/guild/initialize")[0] == 200
    assert call("POST", "/api/guild/initialize")[0] == 200
    purchase = "/enterprise/1/buy-resources"
    assert call("POST", purchase, {"amount": -1})[0] == 422
    assert call("POST", purchase, {"amount": 11})[0] == 409
    assert call("POST", purchase, {"amount": 3})[0] == 303
    response = json.loads(call("GET", "/api/guild")[1])
    assert all(q["progress"] == 3 for q in response["quests"] if "деревини" in q["description"])
    with sessions() as db:
        assert db.get(User, 1).gold == 94
        assert db.get(User, 1).wood == 3
        assert db.get(Enterprise, 1).resource_stored == 7
    with sessions.begin() as db:
        db.get(User, 1).map_sector = "Forest"
    assert call("GET", "/api/guild")[0] == 403


def test_quest_file_changes_only_new_instances(sessions, tmp_path, monkeypatch):
    from backend.services import guild_content

    with sessions.begin() as db:
        guild.initialize(db, 1)
    with sessions() as db:
        original = guild.board(db, 1)["quests"]

    templates = json.loads(guild_content.QUESTS_FILE.read_text(encoding="utf-8"))
    for template in templates:
        template["required"] = 20
        template["gold"] = 77
    templates[0]["key"] = "new_supply"
    content_file = tmp_path / "guild_quests.json"
    content_file.write_text(json.dumps(templates), encoding="utf-8")
    monkeypatch.setattr(guild_content, "QUESTS_FILE", content_file)

    with sessions.begin() as db:
        guild.initialize(db, 2)
        guild.replace(db, 1, original[0]["id"], False)
        db.flush()
        player_quests = guild.board(db, 1)["quests"]
        assert player_quests[1:] == original[1:]
        assert player_quests[0]["required"] == 20
        assert player_quests[0]["gold"] == 77
        assert all(quest["required"] == 20 for quest in guild.board(db, 2)["quests"])
        assert db.get(GuildQuestTemplate, "new_supply") is not None
