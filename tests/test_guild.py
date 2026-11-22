import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from datetime import date
from threading import Barrier
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import database, db_base
from backend.guild_models import ActivityGuildProgress, GuildProgress, GuildQuest, GuildQuestTemplate
from backend.config import SYSTEM_PLAYER_ID
from backend.models import Enterprise, RewardTransaction, User
from backend.routers import admin, adventure_guild, enterprise, map as world_map, player
from backend.services import activity_guilds, guild, world


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'guild.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    factory = sessionmaker(engine, autoflush=False)
    with factory.begin() as db:
        db.add_all([
            User(id=10, username="reader", level=8, gold=100, session_id="reader-session"),
            User(id=2, username="other", gold=100, session_id="other-session"),
            Enterprise(id=1, name="Sawmill", resource_type="singing_resin", resource_stored=10, item_price=2),
        ])
    yield factory
    engine.dispose()


def test_progress_rewards_and_snapshots(sessions):
    with sessions.begin() as db:
        guild.initialize(db, 10)
        guild.initialize(db, 2)
    with sessions.begin() as db:
        initial = guild.board(db, 10)
        assert initial["level"] == 1
        assert len(initial["quests"]) == 5
        frozen = initial["quests"][-1]
        guild.record_collection(db, 10, "small-purchase", "singing_resin", 1)
    with sessions.begin() as db:
        guild.record_collection(db, 10, "small-purchase", "singing_resin", 1)
        db.flush()
        assert all(q["progress"] <= 1 for q in guild.board(db, 10)["quests"])
        assert all(q["progress"] == 0 for q in guild.board(db, 2)["quests"])
        guild.record_collection(db, 10, "wood-purchase", "singing_resin", 20)
        guild.record_collection(db, 10, "stone-purchase", "basalt_bone", 20)
    with sessions.begin() as db:
        completed = guild.board(db, 10)["quests"]
        assert all(q["status"] == "completed" for q in completed)
        with pytest.raises(guild.GuildError, match="Завершений"):
            guild.replace(db, 10, completed[0]["id"], True)
        for quest in completed[:-1]:
            guild.claim(db, 10, quest["id"])
            db.flush()
        after = guild.board(db, 10)
        assert after["level"] == 2
        assert after["next_xp"] == guild.xp_threshold(2)
        assert after["xp"] == sum(q["xp"] for q in completed[:-1]) - guild.xp_threshold(1)
        assert after["claimed_count"] == 4
        assert db.get(User, 10).gold == 100 + sum(q["gold"] for q in completed[:-1])
        assert db.get(User, 10).singing_resin == sum(q["singing_resin"] for q in completed[:-1])
        assert db.get(User, 10).basalt_bone == sum(q["basalt_bone"] for q in completed[:-1])
        assert db.get(User, 10).level == 8
        assert after["quests"][-1]["required"] == frozen["required"]
        assert after["quests"][-1]["gold"] == frozen["gold"]
        generated = db.get(GuildQuest, after["quests"][3]["id"])
        assert generated.generation_level == 2
        template = db.get(GuildQuestTemplate, generated.template_key)
        assert generated.required > template.required
        assert generated.xp > template.xp
        with pytest.raises(guild.GuildError) as duplicate:
            guild.claim(db, 10, completed[0]["id"])
        assert duplicate.value.status_code == 409
        with pytest.raises(guild.GuildError) as wrong_player:
            guild.claim(db, 2, completed[-1]["id"])
        assert wrong_player.value.status_code == 404


def test_replacements_and_utc_reset(sessions, monkeypatch):
    monkeypatch.setattr(guild, "utc_today", lambda: date(2026, 11, 18))
    with sessions.begin() as db:
        guild.initialize(db, 10)
        db.flush()
        guild.record_collection(db, 10, "partial", "singing_resin", 1)
        db.flush()
        before = guild.board(db, 10)
        partial = next(q for q in before["quests"] if q["progress"])
        with pytest.raises(guild.GuildError, match="Підтвердьте"):
            guild.replace(db, 10, partial["id"], False)
        guild.replace(db, 10, partial["id"], True)
        db.flush()
        replacement = guild.board(db, 10)["quests"][partial["slot"] - 1]
        assert replacement["progress"] == 0
        old = db.get(GuildQuest, partial["id"])
        assert old.status == "replaced"
        assert old.template_key != db.get(GuildQuest, replacement["id"]).template_key
        for quest in [q for q in before["quests"] if q != partial][:2]:
            guild.replace(db, 10, quest["id"], True)
            db.flush()
        exhausted = guild.board(db, 10)
        assert exhausted["replacements_remaining"] == 0
        assert exhausted["replacement_reset_at"] == "2026-11-19T00:00:00+00:00"
        with pytest.raises(guild.GuildError, match="вичерпано"):
            guild.replace(db, 10, replacement["id"], False)
        monkeypatch.setattr(guild, "utc_today", lambda: date(2026, 11, 19))
        assert guild.board(db, 10)["replacements_remaining"] == 3
        guild.replace(db, 10, replacement["id"], False)
        assert guild.board(db, 10)["replacements_remaining"] == 2


@pytest.mark.parametrize("operation, successes", [("claim", 1), ("replace", 3)])
def test_concurrent_mutations(sessions, operation, successes):
    with sessions.begin() as db:
        guild.initialize(db, 10)
        db.flush()
        if operation == "claim":
            guild.record_collection(db, 10, "wood-win", "singing_resin", 20)
            guild.record_collection(db, 10, "stone-win", "basalt_bone", 20)
            db.flush()
        quests = guild.board(db, 10)["quests"]

    barrier = Barrier(5)

    def attempt(quest):
        barrier.wait(timeout=5)
        try:
            with sessions.begin() as db:
                if operation == "claim":
                    guild.claim(db, 10, quest["id"])
                else:
                    guild.replace(db, 10, quest["id"], False)
        except guild.GuildError:
            return False
        return True

    inputs = [quests[0]] * 5 if operation == "claim" else quests
    with ThreadPoolExecutor(max_workers=5) as workers:
        assert sum(workers.map(attempt, inputs)) == successes
    with sessions() as db:
        result = guild.board(db, 10)
        assert len(result["quests"]) == 5
        if operation == "claim":
            assert result["claimed_count"] == 1
            assert db.get(User, 10).gold == 100 + quests[0]["gold"]
            reward = db.scalars(select(RewardTransaction)).one()
            assert reward.issuer_id == SYSTEM_PLAYER_ID
            assert reward.recipient_id == 10
            assert reward.gold == quests[0]["gold"]
            assert db.get(User, SYSTEM_PLAYER_ID).gold == 0
        else:
            assert result["replacements_remaining"] == 0


async def asgi_request(app, method, path, cookie, form=None, payload=None):
    messages = []
    path, _, query = path.partition("?")
    headers = [(b"cookie", cookie.encode())]
    data = b""
    if form:
        data = urlencode(form).encode()
        headers.append((b"content-type", b"application/x-www-form-urlencoded"))
    if payload is not None:
        data = json.dumps(payload).encode()
        headers.append((b"content-type", b"application/json"))

    async def receive():
        return {"type": "http.request", "body": data}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "method": method, "path": path, "query_string": query.encode(),
        "headers": headers, "scheme": "http", "server": ("testserver", 80),
    }, receive, send)
    return messages[0]["status"], messages[-1]["body"]


def test_purchase_endpoint_and_guild_auth(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(adventure_guild.router)
    app.include_router(enterprise.router)
    app.include_router(player.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, form=None, cookie="session_id=reader-session"):
        return asyncio.run(asgi_request(app, method, path, cookie, form))

    assert call("GET", "/api/guild", cookie="username=reader")[0] == 401
    status, profile = call("GET", "/player_info?id=1", cookie="")
    assert status == 200
    assert "володар лісу" in profile.decode()
    assert "Системний персонаж" in profile.decode()
    status, page = call("GET", "/guild")
    assert status == 200
    assert 'id="guild-quests"' in page.decode()
    assert call("POST", "/api/guild/initialize")[0] == 200
    assert call("POST", "/api/guild/initialize")[0] == 200
    purchase = "/enterprise/1/buy-resources"
    assert call("POST", purchase, {"amount": -1})[0] == 422
    assert call("POST", purchase, {"amount": 11})[0] == 409
    assert call("POST", purchase, {
        "amount": 3, "expected_price": 2, "expected_total": 7, "request_key": str(uuid4()),
    })[0] == 303
    response = json.loads(call("GET", "/api/guild")[1])
    assert all(q["progress"] == 3 for q in response["quests"] if "співочої смоли" in q["description"])
    with sessions() as db:
        assert db.get(User, 10).gold == 93
        assert db.get(User, 10).singing_resin == 3
        assert db.get(Enterprise, 1).resource_stored == 7
    with sessions.begin() as db:
        db.get(User, 10).map_sector = "Forest"
    assert call("GET", "/api/guild")[0] == 403


def test_quest_file_changes_only_new_instances(sessions, tmp_path, monkeypatch):
    from backend.services import guild_content

    with sessions.begin() as db:
        guild.initialize(db, 10)
    with sessions() as db:
        original = guild.board(db, 10)["quests"]

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
        guild.replace(db, 10, original[0]["id"], False)
        db.flush()
        player_quests = guild.board(db, 10)["quests"]
        assert player_quests[1:] == original[1:]
        assert player_quests[0]["required"] == 20
        assert player_quests[0]["gold"] == 77
        assert all(quest["required"] == 20 for quest in guild.board(db, 2)["quests"])
        assert db.get(GuildQuestTemplate, "new_supply") is not None


def test_world_locations_protect_enterprises_and_guild(sessions, monkeypatch):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    for router in (admin, adventure_guild, enterprise, world_map):
        app.include_router(router.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db
    clock = datetime(2026, 11, 18, 12)
    monkeypatch.setattr(world, "utc_now", lambda: clock)

    def call(method, path, form=None, payload=None, cookie="session_id=reader-session"):
        return asyncio.run(asgi_request(app, method, path, cookie, form, payload))

    with sessions.begin() as db:
        db.get(User, 10).is_admin = True
        db.add(Enterprise(id=2, name="Mine", sector="Forest", resource_type="basalt_bone",
                          resource_stored=10, item_price=2))

    assert call("GET", "/map")[0] == 200
    assert call("POST", "/move", payload={"direction": "e"})[0] == 404
    assert call("GET", "/admin/world")[0] == 200
    locked_sector = {"key": "Ruins", "name": "Руїни"}
    assert call("POST", "/admin/world/sectors", locked_sector, cookie="session_id=other-session")[0] == 403
    assert call("POST", "/admin/world/sectors", locked_sector)[0] == 303
    assert call("POST", "/admin/world/connections", {
        "origin": "Castle", "destination": "Ruins", "duration_seconds": 6,
    })[0] == 303
    assert call("POST", "/move-to-sector", payload={"sector": "Ruins"})[0] == 403
    assert call("POST", "/admin/world/sectors/Ruins/unlock")[0] == 303
    assert any(s["key"] == "Ruins" and s["unlocked"] for s in json.loads(call("GET", "/api/world")[1])["sectors"])
    for endpoint in ("", "/start-work", "/buy-resources"):
        method = "POST" if endpoint else "GET"
        form = {"amount": 1} if endpoint == "/buy-resources" else None
        assert call(method, "/enterprise/2" + endpoint, form)[0] == 403

    status, response = call("POST", "/move-to-sector", payload={"sector": "Forest", "x": 0, "y": 0})
    assert status == 200
    assert json.loads(response)["enterprises"] == []
    assert call("GET", "/api/guild")[0] == 409
    for enterprise_id in (1, 2):
        for endpoint in ("", "/start-work", "/buy-resources"):
            method = "POST" if endpoint else "GET"
            form = {"amount": 1} if endpoint == "/buy-resources" else None
            assert call(method, f"/enterprise/{enterprise_id}" + endpoint, form)[0] == 409

    clock += timedelta(seconds=3)
    assert json.loads(call("GET", "/api/world")[1])["current_sector"] == "Castle"
    assert call("GET", "/enterprise/2")[0] == 409
    clock += timedelta(seconds=1)
    assert call("POST", "/enterprise/2/buy-resources", {
        "amount": 1, "expected_price": 2, "expected_total": 3, "request_key": str(uuid4()),
    })[0] == 303
    assert call("GET", "/enterprise/2")[0] == 200
    assert call("GET", "/enterprise/1")[0] == 403
    with sessions() as db:
        traveler = db.get(User, 10)
        assert (traveler.map_sector, traveler.map_x, traveler.map_y, traveler.gold, traveler.basalt_bone) == (
            "Forest", 83, 50, 97, 1
        )
        assert db.get(User, 2).map_sector == "Castle"


def test_castle_sliders_save_the_army_used_by_battle(sessions):
    from backend.engine import battle_service
    from backend.engine.battle_models import ArmySlot
    from backend.models import CastleBuilding
    from backend.routers import castle

    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(castle.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, form=None):
        return asyncio.run(asgi_request(app, method, "/castle", "session_id=reader-session", form))

    with sessions.begin() as db:
        db.add_all([
            CastleBuilding(player_id=10, building_id="recruitment_tier_3"),
            CastleBuilding(player_id=10, building_id="recruitment_hall"),
            ArmySlot(user_id=10, slot=0, unit_key="peasant", count=7),
            ArmySlot(user_id=10, slot=1, unit_key="knight", count=1),
            ArmySlot(user_id=10, slot=2, unit_key="elves_moon_archer_3", count=2),
        ])
    status, page = call("GET")
    assert status == 200 and b'type="range"' in page
    assert b'data-unit-dialog="unit-info-archer"' not in page
    assert b'id="army-count"' not in page
    assert b'/static/js/dialog.js' in page
    assert b'data-unit-preview="elves_moon_archer_1"' in page
    assert b'data-unit-preview="elves_moon_archer_3"' not in page
    assert b'data-replaces-retained' in page
    assert b'aria-orientation="vertical"' in page
    assert b'id="army-knight"' not in page
    status, info = asyncio.run(asgi_request(app, "GET", "/unit_info?key=archer", ""))
    assert status == 200 and "Очки найму" in info.decode()
    assert "Дальність пострілів" in info.decode() and b"<dd>6</dd>" in info
    assert "Шкода" in info.decode() and 'title="Лучник"' in info.decode()
    assert asyncio.run(asgi_request(app, "GET", "/unit_info?key=unknown", ""))[0] == 404
    assert call("POST", {"knight": 1})[0] == 422
    assert call("POST", {"peasant": 7, "archer": 0, "swordsman": 0})[0] == 422
    assert call("POST", {"elves_moon_archer_1": 99})[0] == 422
    assert b'data-retained-squads="3"' in page
    assert call("POST", {"knight": 0})[0] == 422
    assert call("POST", {"form:elves_moon_archer": "elves_moon_archer_1", "line:elves_moon_archer": 2})[0] == 303
    status, page = asyncio.run(asgi_request(app, "GET", "/castle?saved=1", "session_id=reader-session"))
    assert status == 200 and b'class="army-saved"' in page
    assert "Склад армії збережено".encode() not in page

    with sessions() as db:
        player = db.get(User, 10)
        battle = battle_service.start_pve(db, player, "training")
        army = [(stack["unit"], stack["count"]) for stack in battle["state"]["stacks"].values()
                if stack["owner"] == 0]
        assert army == [("elves_moon_archer_1", 2), ("peasant", 7), ("knight", 1)]


def test_hunts_and_faction_recruitment(sessions):
    from backend.engine import battle_service
    from backend.engine.battle_models import ArmySlot
    from backend.models import CastleBuilding
    from backend.routers.castle import army_options
    from backend.services import world

    with sessions.begin() as db:
        player = db.get(User, 10)
        player.level, player.fraction = 4, "elfe"
        assert "knight" not in {unit["key"] for unit in army_options(db, player)}
        db.add(CastleBuilding(player_id=10, building_id="knight_stables"))
        db.flush()
        assert "knight" not in {unit["key"] for unit in army_options(db, player)}
        assert "skeleton" not in {unit["key"] for unit in army_options(db, player)}
        player.fraction = "undergroundElves"
        assert "skeleton" not in {unit["key"] for unit in army_options(db, player)}
        db.add(CastleBuilding(player_id=10, building_id="ossuary"))
        db.flush()
        assert "skeleton" in {unit["key"] for unit in army_options(db, player)}
        assert "knight" not in {unit["key"] for unit in army_options(db, player)}
        db.add_all([
            ArmySlot(user_id=10, slot=slot, unit_key=key, count=count)
            for slot, (key, count) in enumerate((("peasant", 20), ("archer", 10), ("swordsman", 5)))
        ])

    with sessions.begin() as db:
        other = db.get(User, 2)
        with pytest.raises(battle_service.Forbidden):
            battle_service.start_hunt(db, other, "dragon")
        with pytest.raises(battle_service.NotFound):
            battle_service.start_hunt(db, other, "archer")
        world.start_travel(db, other, "Forest")
    with sessions() as db:
        with pytest.raises(battle_service.Conflict, match="подорожі"):
            battle_service.start_hunt(db, db.get(User, 2), "goblin")

    with sessions() as db:
        player = db.get(User, 10)
        battle = battle_service.start_hunt(db, player, "goblin")
        assert battle["state"]["hunt_key"] == "goblin"
        assert battle["status"] == "deployment"
        battle = battle_service.update_deployment(db, player, battle["id"], battle["version"])
        for _ in range(100):
            if battle["status"] == "finished":
                break
            battle = battle_service.submit_auto_action(db, player, battle["id"], battle["version"])
        assert battle["winner_side"] == 0
        assert any(entry["type"] == "hunters" and entry["amount"] == 1
                   for entry in battle["result"]["sides"][0]["participants"][0]["rewards"])
        db.refresh(player)
        assert 132 <= player.gold <= 398
        before = player.gold
        replay = battle_service.battle_events(db, player, battle["id"], finished_only=True)
        assert replay["initial_state"]["hunt_key"] == "goblin"
        assert player.gold == before
        assert activity_guilds.progress(db, player.id, activity_guilds.HUNTERS)["xp"] == 1


def test_character_dashboard_resources_equipment_and_registered_sections(sessions, tmp_path, monkeypatch):
    from backend.models import EquippedItems, Item, PlayerResourceBalance
    from backend.routers import item as artifact
    from backend.routers import help as game_help
    from backend.engine.data import UNITS
    from backend.routers.battles import battle as battle_pages
    from backend.engine.battle_models import ArmySlot, Battle, BattleParticipant
    from backend.services import character_profile as profile

    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(player.router)
    app.include_router(artifact.router)
    app.include_router(game_help.router)
    app.include_router(battle_pages.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def page(cookie="session_id=reader-session"):
        status, body = asyncio.run(asgi_request(app, "GET", "/player?id=2", cookie))
        return status, body.decode()

    with sessions.begin() as db:
        hero = db.get(User, 10)
        hero.level, hero.experience, hero.stamina = 2, 1500, 9
        hero.gold, hero.singing_resin, hero.basalt_bone = 1200, 17, 19
        db.add(ArmySlot(user_id=10, slot=0, unit_key="archer", count=7))
        db.add(PlayerResourceBalance(player_id=10, resource_id="whisper_dust", quantity=31))
        db.add(PlayerResourceBalance(player_id=10, resource_id="reserved_resource_7", quantity=11))
        item = Item(name="Срібний шолом", owner_id=10, stats={"physical_defense": 3})
        db.add(item)
        db.flush()
        item_id = item.id
        db.add(EquippedItems(user_id=10, helmet_id=item_id))
        guild.initialize(db, 10)
        guild_progress = db.get(GuildProgress, 10)
        guild_progress.level, guild_progress.xp, guild_progress.next_xp = 2, 138, 150
        db.add(ActivityGuildProgress(player_id=10, guild=activity_guilds.workshop_key("jewelry"), points=12))
        db.add(Battle(id=71, mode="pve", status="finished", state={}, initial_state={}))
        db.flush()
        db.add(BattleParticipant(battle_id=71, side=0, user_id=10))
        db.add(RewardTransaction(issuer_id=SYSTEM_PLAYER_ID, recipient_id=10, source="battle_v1",
                                 source_key="71", gold=83, wood=0, stone=0, created_at=datetime(2026, 11, 21)))

    assert page("username=reader")[0] == 401
    status, html = page()
    assert status == 200
    assert 'id="hero-name" title="reader"><a href="/player_info?id=10">reader<' in html
    assert "/upload-avatar" not in html
    assert html.count('class="hero-army-slot') == 8
    assert '<a class="hero-link" href="/castle?section=army">Набрати війська</a>' in html
    assert "Очки армії" not in html and "Налаштувати склад армії" not in html
    assert html.index("Гільдії") < html.index("Спорядження")
    status, public = asyncio.run(asgi_request(app, "GET", "/player_info?id=10", ""))
    assert status == 200
    assert b'class="hero-dashboard hero-public-profile"' in public and b'hero-gear-editor' not in public
    assert b'/update-attribute' not in public
    public_html = public.decode()
    assert public_html.count('class="hero-army-slot') == 8
    assert "Набрати війська" not in public_html
    assert "Гільдія авантюристів" in public_html and "Статистика" in public_html
    assert "/battle/history?player_id=10" in public_html and "/player_info/transfers?id=10" in public_html
    status, battles = asyncio.run(asgi_request(app, "GET", "/battle/history?player_id=10", ""))
    assert status == 200 and "Бій №71" in battles.decode() and b"/battle?replay=71" not in battles
    status, transfers = asyncio.run(asgi_request(app, "GET", "/player_info/transfers?id=10", ""))
    assert status == 200 and "Золото · 83" in transfers.decode()
    assert f'data-hero-slot="head" href="/art_info?id={item_id}"' in html
    assert f'data-hero-slot="head" href="/art_info?id={item_id}"'.encode() in public
    assert 'data-hero-slot="belt" href="/inventory"' in html
    assert b'data-hero-slot="belt" href="/inventory"' not in public
    status, detail = asyncio.run(asgi_request(app, "GET", f"/art_info?id={item_id}", ""))
    assert status == 200 and "Срібний шолом" in detail.decode()
    assert b'class="hero-panel artifact-card"' in detail
    assert asyncio.run(asgi_request(app, "GET", "/art_info?id=-1", ""))[0] == 404
    assert 'value="1500" max="3000"' in html and "Бойовий рівень 2" in html
    assert "Знання" in html and "Витривалість" not in html and "Срібний шолом" in html
    assert 'data-hero-stat="defense"' in html and "спорядження 3" in html
    assert html.count("data-hero-slot=") == 11
    assert html.count("data-resource-id=") == 6
    assert html.index('data-resource-id="gold"') < html.index("</nav>")
    assert "1,200" in html and "Співоча смола · 17" in html and "Шепіт-пил · 31" in html
    assert "reserved_resource_7" not in html
    assert "Вміння з’являться згодом." in public_html
    assert "<h2>Вміння</h2>" not in html and "Останній бій" not in html
    assert 'href="/inventory"' in html
    services_html = html.split("<h2>Сервіси</h2>", 1)[1].split("</section>", 1)[0]
    assert 'href="/help">Довідка по грі</a>' in services_html
    status, help_body = asyncio.run(asgi_request(app, "GET", "/help", ""))
    assert status == 200
    assert b'<template id="help-creatures">' in help_body
    for unit in UNITS.values():
        assert f'href="/unit_info?key={unit.key}"'.encode() in help_body
        assert unit.name.encode() in help_body
    for profile_html in (html, public_html):
        assert 'data-unit-dialog="unit-info-archer"' in profile_html
        assert 'data-unit-dialog="unit-info-peasant"' not in profile_html
        assert 'id="unit-info-archer"' in profile_html
        assert 'href="/guild"' not in profile_html and "Доступна в Замку." not in profile_html
        assert '<strong class="hero-guild-level" aria-label="Рівень 2">2</strong>' in profile_html
        assert 'title="Поточні очки гільдії">138<' in profile_html
        assert 'title="Очки до наступного рівня">+12<' in profile_html
        assert '<progress value="138" max="150" aria-label="Прогрес до наступного рівня · Гільдія авантюристів">' in profile_html
        assert "Братство ловців" in profile_html and "Спілка трудівників" in profile_html
        assert "Колегія металознавців" in profile_html
        assert '<details class="hero-guild-workshops">' in profile_html
        assert '<progress value="12" max="100" aria-label="Прогрес до наступного рівня · Ювелірна справа">' in profile_html
        assert 'aria-label="Прогрес до наступного рівня · Кузня"' not in profile_html

    catalog = json.loads(profile.RESOURCE_FILE.read_text(encoding="utf-8"))
    catalog["unique"].update(name="Тестовий ресурс", active=True)
    resource_file = tmp_path / "profile_resources.json"
    resource_file.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(profile, "RESOURCE_FILE", resource_file)
    monkeypatch.setattr(profile, "GUILDS", ())
    monkeypatch.setattr(profile, "FACTION_SKILLS", (
        profile.ProgressFeature("test-faction", "Тестове вміння",
                                lambda db, hero: {"available": True, "level": 3, "xp": 4, "next_xp": 8}),
    ))
    monkeypatch.setattr(profile, "SERVICES", profile.SERVICES + (
        profile.Service("unavailable", "Прихований сервіс", "/unavailable", 99, available=lambda hero: False),
    ))
    _, html = page()
    assert html.count("data-resource-id=") == 7
    assert "Тестовий ресурс · 11" in html
    assert "Поки немає доступних гільдій." in html
    assert "Тестове вміння" not in html
    status, public = asyncio.run(asgi_request(app, "GET", "/player_info?id=10", ""))
    public_html = public.decode()
    assert status == 200 and "Тестове вміння" in public_html and 'value="4" max="8"' in public_html
    assert public_html.count("data-resource-id=") == 6
    assert "Тестовий ресурс" not in public_html and "reserved_resource_7" not in public_html
    assert 'href="/unavailable"' not in html
    assert page("session_id=other-session")[1].count("data-resource-id=") == 6
    with sessions.begin() as db:
        db.get(PlayerResourceBalance, (10, "reserved_resource_7")).quantity = 0
    assert page()[1].count("data-resource-id=") == 6


def test_hero_endpoints_validate_equipment_and_update_stats_and_army(sessions):
    from backend.models import CastleBuilding, Item

    app = FastAPI()
    app.include_router(player.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, payload=None):
        status, body = asyncio.run(asgi_request(app, method, path, "session_id=reader-session", payload=payload))
        return status, json.loads(body)

    with sessions.begin() as db:
        db.add_all([
            CastleBuilding(player_id=10, building_id="recruitment_tier_3"),
            Item(id=41, owner_id=10, name="Пояс", item_type="belt", stats={"luck": 2, "physical_defense": 3}),
            Item(id=42, owner_id=2, name="Чужий пояс", item_type="belt"),
        ])

    assert call("POST", "/hero/equip", {"slot": "belt", "item_id": 42})[0] == 404
    assert call("POST", "/hero/equip", {"slot": "acc_1", "item_id": 41})[0] == 422
    status, state = call("POST", "/hero/equip", {"slot": "belt", "item_id": 41})
    assert status == 200 and len(state["equipment"]) == 11
    assert state["equipment"]["belt"]["item"]["id"] == 41
    assert state["attributes"]["luck"]["total"] == 2
    assert state["attributes"]["defense"]["total"] == 3
    assert call("GET", "/hero/state")[1] == state
    status, state = call("POST", "/hero/equip", {"slot": "belt", "item_id": None})
    assert status == 200 and state["attributes"]["defense"]["total"] == 0
    assert call("POST", "/hero/army/update", {"counts": {"peasant": 99}})[0] == 422
    assert call("POST", "/hero/army/update", {"counts": {"elves_moon_archer_2": 7}})[0] == 422
    status, state = call("POST", "/hero/army/update", {"counts": {"elves_moon_archer_1": 7}})
    assert status == 200 and state["army"]["spent"] == 1
    assert state["army"]["squads"][0]["key"] == "elves_moon_archer_1"
    assert state["army"]["squads"][0]["count"] == 7


def test_work_and_metalworking_award_points_for_successful_actions(sessions, monkeypatch, tmp_path):
    from backend.models import Item, PlayerResourceBalance
    from backend.routers import castle
    from backend.services import castle_buildings

    buildings = json.loads(castle_buildings.CATALOG_FILE.read_text(encoding="utf-8"))
    entries = {building["id"]: building for building in buildings}
    entries["forge"]["resources"] = {"gold": 500, "basalt_bone": 10, "pulse_spark": 10}
    entries["magic_school_1"]["resources"] = {"gold": 750, "singing_resin": 10, "basalt_bone": 10}
    buildings.extend([
        {"id": "forest_tower", "name": "Лісова вежа", "factions": ["elfe"], "min_level": 9,
         "image_url": "/static/images/buildings/forest_tower.png"},
        {"id": "dark_tower", "name": "Темна вежа", "factions": ["undergroundElves"], "min_level": 1},
    ])
    catalog_file = tmp_path / "castle_buildings.json"
    catalog_file.write_text(json.dumps(buildings), encoding="utf-8")
    monkeypatch.setattr(castle_buildings, "CATALOG_FILE", catalog_file)

    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(castle.router)
    app.include_router(enterprise.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, form=None):
        return asyncio.run(asgi_request(app, method, path, "session_id=reader-session", form))

    with sessions.begin() as db:
        player = db.get(User, 10)
        player.gold, player.singing_resin, player.basalt_bone = 1250, 10, 20
        db.add_all([
            PlayerResourceBalance(player_id=10, resource_id="pulse_spark", quantity=10),
            Item(id=101, name="Перстень", item_type="jewelry", owner_id=10, durability=0, max_durability=100),
            Item(id=102, name="Лук", item_type="bow", owner_id=2, durability=0, max_durability=100),
            ActivityGuildProgress(player_id=10, guild=activity_guilds.METALWORKERS, points=99),
        ])

    assert call("POST", "/enterprise/1/start-work")[0] == 200
    assert call("POST", "/enterprise/1/start-work")[0] == 400
    status, body = call("GET", "/castle")
    assert status == 200 and b'href="/castle/metalworking"' not in body
    assert b'data-castle-dialog="castle-magic"' not in body
    built_section = body.split(b'<details class="castle-built-list">', 1)[1].split(b"</details>", 1)[0]
    assert b'class="castle-building-card"' not in built_section
    assert b'/static/images/buildings/forest_tower.png' in body
    assert b'/static/images/resources/00_gold.png' in body
    assert b'class="castle-section castle-build-action"' in body
    assert "Лісова вежа" in body.decode() and "Темна вежа" not in body.decode()
    assert call("POST", "/castle/build", {"building_id": "forest_tower"})[0] == 403
    assert call("POST", "/castle/build", {"building_id": "dark_tower"})[0] == 404
    assert call("GET", "/castle/metalworking")[0] == 403
    def forge_button(html):
        return html.split(b'name="building_id" value="forge"', 1)[1].split(b">", 1)[0]

    assert b"disabled" not in forge_button(body)
    with sessions.begin() as db:
        db.get(PlayerResourceBalance, (10, "pulse_spark")).quantity = 9
    assert b"disabled" in forge_button(call("GET", "/castle?section=building")[1])
    assert call("POST", "/castle/build", {"building_id": "forge"})[0] == 409
    with sessions.begin() as db:
        db.get(PlayerResourceBalance, (10, "pulse_spark")).quantity = 10
    assert call("POST", "/castle/build", {"building_id": "forge"})[0] == 303
    assert call("POST", "/castle/build", {"building_id": "forge"})[0] == 409
    assert call("POST", "/castle/build", {"building_id": "magic_school_1"})[0] == 303

    status, body = call("GET", "/castle?section=army")
    assert status == 200 and b'href="/castle/metalworking"' in body
    assert b'data-open-on-load' in body and b'id="choose-units-form"' in body
    for section in (b"building", b"army", b"skills", b"magic"):
        assert b'data-castle-dialog="castle-' + section + b'"' in body
    endpoint = "/castle/metalworking/repair"
    unlock = "/castle/metalworking/unlock"
    assert call("POST", endpoint, {"item_id": 101, "durability": 0})[0] == 403
    assert call("POST", unlock, {"workshop": "jewelry"})[0] == 303
    assert call("POST", unlock, {"workshop": "forge"})[0] == 409
    status, body = call("GET", "/castle/metalworking")
    assert status == 200 and "Перстень" in body.decode() and "Зачарувальня" in body.decode()
    assert all(icon.encode() in body for icon in activity_guilds.WORKSHOP_ICONS.values())

    with sessions.begin() as db:
        db.get(ActivityGuildProgress, (10, activity_guilds.workshop_key("jewelry"))).points = 99

    assert call("POST", endpoint, {"item_id": 102, "durability": 0})[0] == 409
    assert call("POST", endpoint, {"item_id": 101, "durability": 0})[0] == 303
    assert call("POST", unlock, {"workshop": "forge"})[0] == 303
    assert call("POST", unlock, {"workshop": "armor"})[0] == 409
    assert call("POST", endpoint, {"item_id": 101, "durability": 0})[0] == 409
    assert call("POST", endpoint, {"item_id": 101, "durability": 5})[0] == 303

    with sessions() as db:
        player = db.get(User, 10)
        assert (player.gold, player.singing_resin, player.basalt_bone) == (0, 0, 0)
        assert db.get(PlayerResourceBalance, (10, "pulse_spark")).quantity == 0
        assert db.get(Item, 101).durability == 15
        assert db.get(Item, 102).durability == 0
        assert activity_guilds.progress(db, 10, activity_guilds.WORKERS)["xp"] == 1
        metalworking = activity_guilds.progress(db, 10, activity_guilds.METALWORKERS)
        assert (metalworking["level"], metalworking["xp"]) == (2, 1)
        workshops = activity_guilds.workshop_progress(db, 10)
        assert (workshops["jewelry"]["level"], workshops["forge"]["level"]) == (1, 0)

    with sessions.begin() as db:
        db.get(ActivityGuildProgress, (10, activity_guilds.METALWORKERS)).points = 250
    assert call("POST", unlock, {"workshop": "armor"})[0] == 303
    assert call("POST", unlock, {"workshop": "enchanting"})[0] == 409
    with sessions.begin() as db:
        db.get(ActivityGuildProgress, (10, activity_guilds.METALWORKERS)).points = 450
    assert call("POST", unlock, {"workshop": "enchanting"})[0] == 303
    with sessions() as db:
        assert set(activity_guilds.workshop_progress(db, 10)) == set(activity_guilds.WORKSHOPS)
    assert [activity_guilds.repair_percent(level) for level in range(11)] == [5, *range(10, 100, 10), 95]


def test_faction_forms_school_summoning_and_replay(sessions, monkeypatch):
    from backend.engine import battle_api, battle_service
    from backend.engine.battle_models import ArmySlot
    from backend.engine.events import reconstruct
    from backend.engine.summoning import squad_health
    from backend.models import CastleBuilding, Item
    from backend.routers import castle, help as game_help
    from backend.services.character_profile import hero_state
    from backend.services.hero_equipment import change_equipment

    assert squad_health(67, 20) == (4, 7)
    assert squad_health(60, 20) == (3, 20)
    assert squad_health(0, 20) == (0, 0)
    monkeypatch.setattr(battle_service.secrets, "randbits", lambda _: 42)
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    for router in (castle.router, battle_api.router, game_help.router):
        app.include_router(router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, *, form=None, payload=None, token="reader-session"):
        return asyncio.run(asgi_request(app, method, path, f"session_id={token}", form, payload))

    status, body = call("GET", "/creatures/catalog")
    catalog = json.loads(body)
    assert status == 200
    for faction, lines in catalog["factions"].items():
        assert len(lines) == 8 and [line["tier"] for line in lines] == list(range(1, 9))
        for line in lines:
            assert [form["form"] for form in line["forms"]] == [1, 2, 3]
            base = f"{faction}_recruitment_tier_{line['tier']}"
            assert line["recruitment"]["building"] == base
            assert [form["building"] for form in line["forms"][1:]] == [f"{base}_form_2", f"{base}_form_3"]
            assert f"{faction}_{line['key']}_3" in catalog["units"]
    assert len(catalog["summoning"]["elementals"]) == 6

    with sessions.begin() as db:
        elf = db.get(User, 10)
        elf.fraction, elf.mind, elf.magic_power = "elfe", 0, 3
        elf.melee_attack = 2
        elf.gold, elf.basalt_bone = 10000, 100
        elf.singing_resin = 200
        other = db.get(User, 2)
        other.fraction = "undergroundElves"
        other.gold, other.singing_resin, other.basalt_bone = 500, 20, 10
        db.add_all([
            Item(id=103, owner_id=10, item_type="belt", stats={
                "mind": 1, "magic_power": 2, "melee_attack": 3, "physical_defense": 4,
                "initiative": 1, "luck": 2, "morale": 1,
            }),
            CastleBuilding(player_id=10, building_id="magic_school_1"),
            CastleBuilding(player_id=10, building_id="magic_school_2"),
            CastleBuilding(player_id=2, building_id="magic_school_1"),
            ArmySlot(user_id=2, slot=0, unit_key="underground_elves_shade_1", count=20),
        ])
        db.flush()
        change_equipment(db, elf, slot="belt", item_id=103)
        db.flush()
        profile_stats = {key: stat["total"] for key, stat in hero_state(db, elf)["attributes"].items()}

    status, body = call("GET", "/castle?section=army")
    assert status == 200 and b'name="form:elves_sylven"' not in body
    assert b'name="form:underground_elves_shade"' not in body
    assert call("POST", "/castle/build", form={"building_id": "magic_school_4"})[0] == 403
    assert call("POST", "/api/battles/pve", payload={"scenario": "training"})[0] == 400
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3"})[0] == 403
    with sessions.begin() as db:
        db.get(User, 10).level = 3
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3_outpost"})[0] == 303
    status, body = call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3"})
    assert status == 403 and "Потрібен бойовий рівень 5".encode() in body
    assert b'name="form:elves_moon_archer"' not in call("GET", "/castle?section=army")[1]
    with sessions.begin() as db:
        db.get(User, 10).level = 8
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3"})[0] == 303
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3_form_3"})[0] == 403
    assert call("POST", "/castle", form={
        "form:elves_moon_archer": "elves_moon_archer_2", "line:elves_moon_archer": 10,
    })[0] == 422
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3_form_2"})[0] == 303
    status, body = call("GET", "/castle?section=army")
    assert status == 200 and b'<select id="army-form-' not in body
    assert b'type="radio" name="form:elves_moon_archer" value="elves_moon_archer_2"' in body
    assert b'<span class="unit-portrait" title="' in body.split(b'data-army-form', 1)[1].split(b'</label>', 1)[0]
    assert b'value="elves_moon_archer_3"' not in body
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3_form_3"})[0] == 403
    with sessions.begin() as db:
        db.get(User, 10).level = 12
        db.get(User, 2).level = 5
    assert call("POST", "/castle/build", form={"building_id": "elves_recruitment_tier_3_form_3"})[0] == 303
    assert call("POST", "/castle", form={
        "form:elves_moon_archer": "elves_moon_archer_3", "line:elves_moon_archer": 10,
    })[0] == 303
    assert call("POST", "/castle", form={
        "form:elves_moon_archer": "underground_elves_toxin_sting_3", "line:elves_moon_archer": 10,
    })[0] == 422

    assert call("POST", "/castle/build", form={"building_id": "magic_school_2"}, token="other-session")[0] == 303
    status, body = call("POST", "/api/battles/pve", payload={"scenario": "training"}, token="other-session")
    assert status == 200
    underground = json.loads(body)["state"]
    assert set(underground["heroes"]) == {"hero_0"}
    assert not underground["summoning"]["0"]["elements"]

    status, body = call("POST", "/api/battles/pve", payload={"scenario": "training"})
    battle = json.loads(body)
    assert status == 200
    player_army = [stack["unit"] for stack in battle["state"]["stacks"].values() if stack["owner"] == 0]
    assert player_army == ["elves_moon_archer_3"]
    hero = battle["state"]["heroes"]["hero_0"]
    assert {key: hero[key] for key in profile_stats} == profile_stats
    assert (hero["attack"], hero["defense"], hero["knowledge"], hero["spell_power"], hero["initiative"]) == (5, 4, 1, 5, 11)
    assert (hero["damage_min"], hero["damage_max"]) == (10, 13)
    assert battle["state"]["summoning"]["0"]["elements"] == ["earth", "water"]
    root = f"/api/battles/{battle['id']}"
    status, body = call("POST", root + "/begin", payload={"version": battle["version"]})
    assert status == 200
    battle = json.loads(body)

    def summon(element, version):
        return call("POST", root + "/actions", payload={"version": version, "action": {
            "type": "summon", "element": element,
        }})

    def advance_to_hero(current, battle_root):
        for _ in range(12):
            if (current["turn"] or {}).get("hero"):
                return current
            status, body = call("POST", battle_root + "/actions", payload={
                "version": current["version"], "action": {"type": "defend"},
            })
            assert status == 200
            current = json.loads(body)
        pytest.fail("Герой не отримав хід.")

    assert not battle["turn"].get("hero")
    assert any(entry["id"] == "hero_0" for entry in battle["forecast"])
    assert summon("earth", battle["version"])[0] == 400
    battle = advance_to_hero(battle, root)
    options = {spell["element"]: spell for spell in battle["turn"]["spells"]}
    assert set(options) == {"earth", "water"}
    assert options["earth"]["energy_cost"] == 10
    assert options["earth"]["target"]["side"] == 0
    assert options["earth"]["description"] and options["earth"]["target_label"]
    assert summon("fire", battle["version"])[0] == 400
    first_version = battle["version"]
    status, body = summon("earth", first_version)
    assert status == 200
    battle = json.loads(body)
    first = next(stack for stack in battle["state"]["stacks"].values() if stack.get("summoned"))
    assert (first["count"], first["top_hp"], first["x"], first["y"]) == (3, 20, 0, 0)
    assert options["earth"]["target"]["cell"] == [first["x"], first["y"]]
    assert battle["state"]["summoning"]["0"]["energy"] == 10
    assert summon("earth", first_version)[0] == 409

    battle = advance_to_hero(battle, root)
    status, body = summon("water", battle["version"])
    assert status == 200
    battle = json.loads(body)
    summons = [stack for stack in battle["state"]["stacks"].values() if stack.get("summoned")]
    assert len(summons) == 1 and first["id"] not in battle["state"]["stacks"]
    assert summons[0]["unit"] == "elemental_water"
    summoned = next(event["payload"] for event in battle["event_stream"] if event["type"] == "ELEMENTAL_SUMMONED")
    assert (summoned["count"], summoned["top_hp"]) == (4, 10)
    assert battle["state"]["summoning"]["0"]["energy"] == 0
    battle = advance_to_hero(battle, root)
    assert all("target" not in spell and "Недостатньо енергії" in spell["unavailable"]
               for spell in battle["turn"]["spells"])
    status, body = summon("earth", battle["version"])
    assert status == 400 and "Недостатньо енергії" in body.decode()
    status, body = call("GET", root + "/events")
    replay = json.loads(body)
    assert status == 200
    assert sum(event["type"] == "ELEMENTAL_SUMMONED" for event in replay["events"]) == 2
    assert reconstruct(replay["initial_state"], replay["events"]) == battle["state"]
    assert call("POST", root + "/surrender", payload={"version": battle["version"]})[0] == 200

    status, body = call("POST", "/api/battles/hunt/goblin")
    assert status == 200
    hunt = json.loads(body)
    assert hunt["state"]["hunt_key"] == "goblin"
    assert set(hunt["state"]["heroes"]) == {"hero_0"}
    assert hunt["state"]["summoning"]["0"]["elements"] == ["earth", "water"]
    hunt_root = f"/api/battles/{hunt['id']}"
    status, body = call("POST", hunt_root + "/begin", payload={"version": hunt["version"]})
    assert status == 200
    hunt = advance_to_hero(json.loads(body), hunt_root)
    status, body = call("POST", hunt_root + "/actions", payload={
        "version": hunt["version"], "action": {"type": "summon", "element": "water"},
    })
    assert status == 200
    assert json.loads(body)["state"]["summoning"]["0"]["energy"] == 10


def test_registration_grants_only_own_faction_starter_buildings(sessions):
    from backend.engine.roster import saved_army
    from backend.models import CastleBuilding
    from backend.routers import auth, castle

    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(auth.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db
    for username, fraction, group in (
        ("new_elf", "elfe", "elves"),
        ("new_underground", "undergroundElves", "underground_elves"),
    ):
        assert asyncio.run(asgi_request(app, "POST", "/register", "", {
            "username": username, "password": "test-password", "fraction": fraction,
        }))[0] == 303
        with sessions() as db:
            user = db.scalar(select(User).where(User.username == username))
            assert user.fraction == fraction
            ids = db.scalars(select(CastleBuilding.building_id).where(CastleBuilding.player_id == user.id))
            assert set(ids) == {f"{group}_recruitment_tier_{tier}" for tier in (1, 2)}
            assert saved_army(db, user.id) == []
            options = castle.army_options(db, user)
            assert [(item["unit"].tier, item["unit"].form) for item in options] == [(1, 1), (2, 1)]
