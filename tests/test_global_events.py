import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from backend import database
from backend.models import (
    ConstructionContribution, Enterprise, EnterpriseShift, EventConstruction, EventReward,
    GlobalEvent, Item, News, PlayerResourceBalance, RewardTransaction, ShopItem, User,
)
from backend.routers import enterprise, global_events, map, news, player
from backend.services import global_events as service, world
from backend.services.economy import MAX_GOLD
from backend.world_models import WorldSector
from test_guild import asgi_request, sessions


@pytest.fixture
def event_client(sessions):
    app = FastAPI()
    for module in (global_events, news, enterprise, map, player):
        app.include_router(module.router)
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db
    with sessions.begin() as db:
        reader = db.get(User, 10)
        reader.is_admin, reader.singing_resin = True, 200
        db.get(User, 2).singing_resin = 200
        db.add(Enterprise(id=3, name="Кар'єр кісткового каменю", resource_type="basalt_bone",
                          production_type="mine", resource_stored=20, item_price=180, balance=850))

    def call(method, url, payload=None, *, user="reader", form=None):
        return asyncio.run(asgi_request(app, method, url, f"session_id={user}-session" if user else "",
                                        form=form, payload=payload))

    return call


def project(resource="whisper_dust", **options):
    return {"enterprise_type": resource, "requirements": {"singing_resin": 100},
            "area": 100, "salary": 30, "item_price": 44, "max_workers": 3, "max_storage": 60,
            "balance": 1000, **options}


def draft(projects=None, sector="Castle"):
    return {"title": "Спільне будівництво", "summary": "Будуємо шахти", "description": "Опис",
            "rules": "Правила", "completion": "Усі шахти готові", "reward_description": "Нагороди",
            "sector": sector, "image_url": service.stage_images("whisper_dust")["FOUNDATION"],
            "projects": projects or [project()]}


def body(result, status=200):
    assert result[0] == status, result[1]
    return json.loads(result[1])


def new_event(call, projects=None):
    event_id = body(call("POST", "/admin/events", draft(projects)), 201)["id"]
    assert body(call("POST", f"/admin/events/{event_id}/start", {"confirmed": True}))["status"] == "ACTIVE"
    return event_id


def site_ids(sessions, event_id):
    with sessions() as db:
        return [row.enterprise_id for row in service.projects(db, event_id)]


def contribution(call, site_id, quantity, *, user="reader", resource="singing_resin", operation=None):
    return call("POST", f"/enterprise/{site_id}/construction/contribute",
                {"resource": resource, "quantity": quantity, "operation_id": operation or str(uuid4())}, user=user)


def test_draft_launch_permissions_existing_enterprises_and_notice(event_client, sessions):
    call = event_client
    assert b'id="event-draft"' not in call("GET", "/admin/events")[1]
    assert b'id="event-draft"' in call("GET", "/admin/events/new")[1]
    assert call("GET", "/admin/events", user="other")[0] == 403
    assert call("POST", "/admin/events", draft(), user="other")[0] == 403
    with sessions() as db:
        closed = db.scalar(select(WorldSector.key).where(WorldSector.unlocked.is_(False)).limit(1))
    assert call("POST", "/admin/events", draft(sector=closed))[0] == 422
    event_id = body(call("POST", "/admin/events", draft()), 201)["id"]
    path = f"/admin/events/{event_id}"
    assert call("GET", path)[0] == 200
    assert call("GET", f"/events/{event_id}", user="other")[0] == 404
    assert body(call("GET", "/api/news/latest", user="other")) == {"news": None}
    assert call("PATCH", path, {**draft(), "title": "Оновлена подія"})[0] == 200
    assert call("POST", path + "/start", {"confirmed": False})[0] == 422
    assert call("POST", path + "/start", {"confirmed": True}, user="other")[0] == 403
    assert body(call("POST", path + "/start", {"confirmed": True}))["status"] == "ACTIVE"
    assert body(call("POST", path + "/start", {"confirmed": True}))["status"] == "ACTIVE"
    assert call("PATCH", path, draft())[0] == 409
    assert call("GET", path)[0] == 200
    with sessions() as db:
        assert db.get(Enterprise, 1).resource_stored == 10
        assert (db.get(Enterprise, 3).resource_stored, db.get(Enterprise, 3).balance) == (20, 850)
        assert db.scalar(select(func.count(Enterprise.id))) == 3
        assert db.scalar(select(func.count(News.id))) == 1
    first = body(call("GET", "/api/news/latest"))["news"]
    assert first["event_id"] == event_id and first["title"] == "Оновлена подія"
    assert body(call("GET", "/api/news/latest"))["news"] == first
    assert call("POST", f"/api/news/{first['id']}/acknowledge")[0] == 204
    assert body(call("GET", "/api/news/latest"))["news"] is None
    assert body(call("GET", "/api/news/latest", user="other"))["news"] == first
    with sessions.begin() as db:
        db.add(User(id=20, username="late", session_id="late-session"))
    assert body(call("GET", "/api/news/latest", user="late"))["news"] == first
    assert call("GET", "/events?")[0] == 200
    assert call("GET", f"/events/{event_id}?enterprise_id=&resource=")[0] == 200
    site_id, = site_ids(sessions, event_id)
    assert b"construction-panel" in call("GET", f"/enterprise/{site_id}")[1]
    app_map = body(call("GET", "/api/world"))
    site = next(entry for entry in app_map["enterprises"] if entry["id"] == site_id)
    assert site["production_type"] == "mine" and site["construction"]["progress"] == 0
    assert call("POST", f"/enterprise/{site_id}/start-work")[0] == 409
    assert call("POST", f"/enterprise/{site_id}/buy-resources", form={"amount": 1})[0] == 409
    assert call("POST", path + "/cancel", {"confirmed": True})[0] == 200
    assert call("GET", f"/events/{event_id}")[0] == 404


def test_contributions_weighting_price_snapshot_and_deduplication(event_client, sessions):
    call = event_client
    event_id = new_event(call, [project(requirements={"singing_resin": 100, "gold": 10})])
    site, = site_ids(sessions, event_id)
    path = f"/enterprise/{site}/construction"
    assert body(call("GET", path))["stage"] == "FOUNDATION"
    token = str(uuid4())
    first = body(contribution(call, site, 19, operation=token))
    assert first["collection_progress"] == 9.5 and first["stage"] == "FOUNDATION"
    assert body(contribution(call, site, 19, operation=token))["collection_progress"] == 9.5
    assert contribution(call, site, 18, operation=token)[0] == 409
    assert contribution(call, site, 0)[0] == contribution(call, site, -1)[0] == 422
    assert contribution(call, site, 1, resource="basalt_bone")[0] == 422
    assert contribution(call, site, 82)[0] == 409
    with sessions.begin() as db:
        db.get(Enterprise, 1).item_price = 5
        db.get(User, 2).singing_resin = 0
    assert contribution(call, site, 1, user="other")[0] == 409
    second = body(contribution(call, site, 1))
    assert second["collection_progress"] == 10 and second["stage"] == "FOUNDATION_WITH_RESOURCES"
    assert second["started_at"] is None
    assert call("POST", f"/admin/events/{event_id}/cancel", {"confirmed": True})[0] == 409
    with sessions.begin() as db:
        closed = db.scalar(select(WorldSector.key).where(WorldSector.unlocked.is_(False)).limit(1))
        db.get(User, 2).map_sector = closed
    assert contribution(call, site, 1, user="other", resource="gold")[0] == 403
    state = body(contribution(call, site, 80))
    assert state["stage"] == "FOUNDATION_WITH_RESOURCES" and state["started_at"] is None
    assert body(contribution(call, site, 10, resource="gold"))["stage"] == "FRAME_CONSTRUCTION"
    assert contribution(call, site, 1, resource="gold")[0] == 409
    stats = body(call("GET", f"/events/{event_id}/statistics?enterprise_id={site}"))
    assert stats["resources"] == {"singing_resin": 100, "gold": 10}
    assert "value" not in stats and "value" not in stats["personal"]
    assert "percent" not in stats["personal"]
    internal = body(call("GET", f"/admin/events/{event_id}/statistics"))
    assert internal["ranking"][0]["value"] == 19 * 2 + 81 * 5 + 10
    page = call("GET", f"/events/{event_id}")[1]
    assert "Оцінка внесків".encode() not in page
    assert "Активна · Працює".encode() not in page
    assert b" UTC" not in page
    assert b'/static/images/resources/01_singing_resin.png' in page
    assert "Оцінка внесків".encode() in call("GET", f"/admin/events/{event_id}")[1]
    with sessions() as db:
        assert (db.get(User, 10).singing_resin, db.get(User, 10).gold) == (100, 90)
        assert db.scalars(select(ConstructionContribution.unit_price).order_by(
            ConstructionContribution.id)).all() == [2, 5, 5, 1]


def test_concurrent_final_contributions(event_client, sessions):
    event_id = new_event(event_client, [project(requirements={"singing_resin": 10})])
    site, = site_ids(sessions, event_id)
    barrier = Barrier(2)

    def attempt(name):
        barrier.wait(timeout=5)
        return contribution(event_client, site, 10, user=name)[0]

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(attempt, ("reader", "other"))) == [200, 409]
    with sessions() as db:
        assert db.scalar(select(func.count(ConstructionContribution.id))) == 1
        assert db.get(User, 10).singing_resin + db.get(User, 2).singing_resin == 390


def test_independent_timers_resume_and_standard_operations(event_client, sessions, monkeypatch):
    call = event_client
    clock = datetime(2026, 11, 27, 12)
    monkeypatch.setattr(world, "utc_now", lambda: clock)
    selection = [project(requirements={"singing_resin": 10}),
                 project("pulse_spark", requirements={"gold": 20})]
    event_id = new_event(call, selection)
    first, second = site_ids(sessions, event_id)
    assert body(contribution(call, first, 10))["stage"] == "FRAME_CONSTRUCTION"
    clock += timedelta(hours=72, microseconds=-1)
    assert body(call("GET", f"/enterprise/{first}/construction"))["stage"] == "FRAME_CONSTRUCTION"
    clock += timedelta(microseconds=1)
    state = body(call("GET", f"/enterprise/{first}/construction"))
    assert (state["stage"], state["construction_progress"]) == ("BUILDING_CONSTRUCTION", 60)
    assert body(call("GET", f"/enterprise/{second}/construction"))["stage"] == "FOUNDATION"
    assert body(contribution(call, second, 20, user="other", resource="gold"))["stage"] == "FRAME_CONSTRUCTION"
    clock += timedelta(hours=48)
    assert body(call("GET", f"/enterprise/{first}/construction"))["stage"] == "OPERATIONAL"
    assert b"construction-panel" not in call("GET", f"/enterprise/{first}")[1]
    assert call("POST", f"/enterprise/{first}/start-work")[0] == 200
    with sessions.begin() as db:
        assert db.get(GlobalEvent, event_id).status == "ACTIVE"
        site = db.get(Enterprise, first)
        assert site.balance == 970
        shift = db.scalar(select(EnterpriseShift).where(EnterpriseShift.enterprise_id == first))
        from backend.services.enterprises import settle_shift
        settle_shift(db, 10, shift.completes_at)
        assert site.resource_stored == 1
    assert call("POST", f"/enterprise/{first}/buy-resources", user="other",
                form={"amount": 1, "expected_price": 52, "expected_total": 53, "request_key": str(uuid4())})[0] == 303
    clock += timedelta(hours=72)
    # Fresh session materializes missed deadlines from persisted timestamps.
    with sessions.begin() as db:
        service.finish_due(db)
    with sessions() as db:
        assert db.get(GlobalEvent, event_id).status == "COMPLETED"
        builds = db.scalars(select(EventConstruction).order_by(EventConstruction.id)).all()
        assert builds[1].operational_since == clock
        assert builds[0].operational_since == clock - timedelta(hours=72)
        assert db.get(Enterprise, first).balance == 1022
        assert db.get(Enterprise, second).balance == 1000


def test_rewards_preview_partial_retry_isolation_and_notification(event_client, sessions, monkeypatch):
    call = event_client
    clock = datetime(2026, 11, 27, 12)
    monkeypatch.setattr(world, "utc_now", lambda: clock)
    with sessions.begin() as db:
        item = Item(name="Тестовий артефакт", stats={}, durability=5, max_durability=5, item_type="belt")
        db.add(item)
        db.flush()
        listing = ShopItem(price=5, level_required=1, quantity=1, item_template=item)
        db.add(listing)
        db.flush()
        listing_id = listing.id
    event_id = new_event(call, [project(requirements={"singing_resin": 10})])
    site, = site_ids(sessions, event_id)
    path = f"/admin/events/{event_id}/rewards"
    plan = {"multiplier": "1.5", "everyone": {"gold": 10, "resources": {"whisper_dust": 3}},
            "ranks": {"1": {"items": {str(listing_id): 1}}}, "individuals": {"2": {"gold": 4}}}
    assert call("POST", path + "/preview", plan)[0] == 409
    assert contribution(call, site, 6)[0] == 200
    assert contribution(call, site, 4, user="other")[0] == 200
    clock += timedelta(hours=120)
    preview = body(call("POST", path + "/preview", plan))
    assert preview["totals"] == {"gold": 54, "resources": {"whisper_dust": 6}, "items": {str(listing_id): 1}}
    assert call("POST", path + "/issue", {"confirmed": True, "plan": plan}, user="other")[0] == 403
    assert call("POST", path + "/issue", {"confirmed": False, "plan": plan})[0] == 422
    with sessions.begin() as db:
        assert db.get(User, 10).gold == 100
        assert db.get(PlayerResourceBalance, (10, "whisper_dust")) is None
        db.get(User, 2).gold = MAX_GOLD
    assert body(call("POST", path + "/issue", {"confirmed": True, "plan": plan}))["status"] == "COMPLETED"
    rewards = body(call("GET", path))
    assert [row["status"] for row in rewards] == ["ISSUED", "FAILED"]
    assert call("GET", path, user="other")[0] == 403
    with sessions.begin() as db:
        assert db.get(User, 10).gold == 128
        assert db.get(PlayerResourceBalance, (10, "whisper_dust")).quantity == 3
        assert db.scalar(select(Item).where(Item.owner_id == 10)).name == "Тестовий артефакт"
        assert db.get(ShopItem, listing_id).quantity == 1
        assert db.get(PlayerResourceBalance, (2, "whisper_dust")) is None
        db.get(User, 2).gold = 100
    assert body(call("POST", path + "/issue", {"confirmed": True}))["status"] == "REWARDED"
    assert body(call("POST", path + "/issue", {"confirmed": True}))["status"] == "REWARDED"
    with sessions() as db:
        assert db.get(User, 10).gold == 128 and db.get(User, 2).gold == 126
        assert db.scalar(select(func.count(EventReward.id))) == 2
        assert db.scalar(select(func.count(RewardTransaction.id))) == 2
        assert db.get(User, 1).gold == 0
        notification_id = db.scalar(select(News.id).where(News.event_id == event_id, News.recipient_id.is_(None)))
    assert call("POST", f"/api/news/{notification_id}/acknowledge")[0] == 204
    reward_news = body(call("GET", "/api/news/latest"))["news"]
    assert "Золото: 28" in reward_news["text"]
    assert call("POST", f"/api/news/{reward_news['id']}/acknowledge", user="other")[0] == 404
    assert b"global_event" not in call("GET", "/player_info/transfers?id=10")[1]


def test_adopt_and_restore_only_unused_placeholder(event_client, sessions):
    with sessions.begin() as db:
        db.add(Enterprise(id=4, name="Штольня тихого пилу", sector="Castle", resource_type="gold",
                          production_type="mine", balance=1000, salary=30, item_price=11))
        db.add(Enterprise(id=7, name="Кратер видобутку", sector="Castle", resource_type="astralit",
                          production_type="mine", resource_stored=1))
    invalid = body(event_client("POST", "/admin/events", draft([project("astralit", adopt_placeholder=True)])), 201)
    assert event_client("POST", f"/admin/events/{invalid['id']}/start", {"confirmed": True})[0] == 409
    event_id = new_event(event_client, [project(adopt_placeholder=True)])
    assert site_ids(sessions, event_id) == [4]
    with sessions() as db:
        assert db.get(Enterprise, 4).resource_type == "whisper_dust"
    assert event_client("POST", f"/admin/events/{event_id}/cancel", {"confirmed": True})[0] == 200
    with sessions() as db:
        placeholder = db.get(Enterprise, 4)
        assert (placeholder.resource_type, placeholder.item_price, placeholder.salary) == ("gold", 11, 30)
        assert db.get(Enterprise, 7).resource_stored == 1


def test_multiple_mines_of_same_type_with_independent_art_and_balances(event_client, sessions, monkeypatch):
    call = event_client
    clock = datetime(2026, 11, 27, 12)
    monkeypatch.setattr(world, "utc_now", lambda: clock)
    monkeypatch.setattr(enterprise, "utc_now", lambda: clock)
    images = service.stage_images("pulse_spark")
    event_id = new_event(call, [
        project(name="Перша штольня", requirements={"singing_resin": 10}, balance=111, stage_images=images),
        project(name="Друга штольня", requirements={"singing_resin": 30}, balance=222),
        *[project() for _ in range(10)],
    ])
    first, second, *_ = site_ids(sessions, event_id)
    another_event = new_event(call)
    assert site_ids(sessions, another_event)[0] not in site_ids(sessions, event_id)
    path = f"/admin/events/{event_id}/enterprises/{second}/images"
    assert call("PATCH", path, {"stage_images": images}, user="other")[0] == 403
    assert call("PATCH", path, {"stage_images": {"FOUNDATION": "/static/images/missing.png"}})[0] == 422
    assert call("PATCH", path, {"stage_images": {"INVALID": images["FOUNDATION"]}})[0] == 422
    assert body(call("PATCH", path, {"stage_images": {"FOUNDATION": images["FOUNDATION"]}}))[
        "stage_images"]["FOUNDATION"] == images["FOUNDATION"]
    assert images["FOUNDATION"].encode() in call("GET", f"/enterprise/{first}")[1]
    assert images["FOUNDATION"].encode() in call("GET", f"/enterprise/{second}")[1]
    assert body(contribution(call, first, 1))["image_url"] == images["FOUNDATION_WITH_RESOURCES"]
    assert body(contribution(call, first, 9))["image_url"] == images["FRAME_CONSTRUCTION"]
    assert body(contribution(call, second, 30))["stage"] == "FRAME_CONSTRUCTION"
    clock += timedelta(hours=72)
    assert images["BUILDING_CONSTRUCTION"].encode() in call("GET", f"/enterprise/{first}")[1]
    clock += timedelta(hours=48)
    assert images["OPERATIONAL"].encode() in call("GET", f"/enterprise/{first}")[1]
    state = body(call("GET", "/api/world"))
    assert next(entry for entry in state["enterprises"] if entry["id"] == first)["image_url"] == images["OPERATIONAL"]
    with sessions() as db:
        assert db.get(Enterprise, first).balance == 111
        assert db.get(Enterprise, second).balance == 222
        assert db.get(Enterprise, first).name == "Перша штольня"
        assert db.get(Enterprise, second).name == "Друга штольня"


def test_event_page_shows_all_contributors_in_descending_order(event_client, sessions):
    call = event_client
    event_id = new_event(call)
    site, = site_ids(sessions, event_id)
    with sessions.begin() as db:
        for rank in range(1, 28):
            user = User(username=f"Contributor-{rank:02d}", gold=0)
            db.add(user)
            db.flush()
            db.add(ConstructionContribution(
                event_id=event_id, enterprise_id=site, player_id=user.id, resource_id="singing_resin",
                quantity=rank, unit_price=2, value=rank * 2, created_at=world.utc_now(), operation_id=str(uuid4()),
            ))
    status, page = call("GET", f"/events/{event_id}?page=2&resource=gold", user="other")
    assert status == 200 and b"event-filters" not in page
    positions = [page.index(f"Contributor-{rank:02d}".encode()) for rank in range(27, 0, -1)]
    assert positions == sorted(positions)
    assert len(body(call("GET", f"/events/{event_id}/statistics"))["rankings"]) == 25


def test_paused_event_keeps_contributions_and_freezes_construction(event_client, sessions, monkeypatch):
    call = event_client
    now = datetime(2026, 11, 27, 12)
    monkeypatch.setattr(world, "utc_now", lambda: now)
    event_id = new_event(call, [project(requirements={"singing_resin": 10})])
    site, = site_ids(sessions, event_id)
    assert contribution(call, site, 10)[0] == 200
    now += timedelta(hours=24)
    with sessions.begin() as db:
        event = db.get(GlobalEvent, event_id)
        event.status, event.paused_at = "PAUSED", now
    now += timedelta(days=6)
    state = body(call("GET", f"/enterprise/{site}/construction"))
    assert state["paused"] and state["stage"] == "FRAME_CONSTRUCTION"
    assert state["construction_progress"] == 20
    assert contribution(call, site, 1)[0] == 409
    assert body(call("GET", "/events/active")) == []
    assert body(call("GET", "/api/news/latest")) == {"news": None}
    with sessions() as db:
        assert db.get(GlobalEvent, event_id).status == "PAUSED"
        assert db.scalar(select(ConstructionContribution.quantity)) == 10
