import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend import database
from backend.models import Enterprise, EnterpriseDailyReport, EnterpriseEvent, EnterpriseShift, User
from backend.routers import admin, enterprise
from backend.services import economy, enterprises
from test_guild import asgi_request, sessions


def site_client(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(enterprise.router)
    app.include_router(admin.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, suffix="", form=None, player="reader", site=1):
        path = suffix if suffix.startswith("/admin/") else f"/enterprise/{site}{suffix}"
        return asyncio.run(asgi_request(
            app, method, path, f"session_id={player}-session", form,
        ))

    return call


def test_employment_reservation_snapshots_capacity_and_settlement(sessions, monkeypatch):
    policy = enterprises.Rules(
        pricing={}, employment={"multiplier_percent": 150, "penalty_percent": 10},
        enterprises={1: {"units_per_worker": 4}},
    )
    monkeypatch.setattr(enterprises, "rules", lambda: policy)
    now = datetime(2026, 11, 22, 12)
    monkeypatch.setattr(enterprise, "utc_now", lambda: now)
    monkeypatch.setattr(enterprises, "utc_now", lambda: now)
    with sessions.begin() as db:
        site = db.get(Enterprise, 1)
        site.max_workers, site.max_storage, site.salary, site.balance = 1, 30, 40, 36
    call = site_client(sessions)
    key = str(uuid4())
    form = {"request_key": key, "return_to_enterprise": "true"}
    assert call("POST", "/start-work", form)[0] == 303
    assert call("POST", "/start-work", form)[0] == 303
    assert call("POST", "/start-work")[0] == 400
    assert call("POST", "/start-work", player="other")[0] == 400
    assert call("GET")[0] == 200
    assert b"2026-11-22T13:00:00Z" in call("GET")[1]
    with sessions.begin() as db:
        site = db.get(Enterprise, 1)
        shift = enterprises.active_shift(db, 10)
        assert (shift.payable, site.balance, site.workers_count) == (54, 0, 1)
        assert shift.enterprise_payable == 36
        assert db.get(User, 10).gold == 100
        site.salary = 999
    now += enterprises.SHIFT_DURATION
    assert call("GET", player="other")[0] == 200
    assert call("GET")[0] == 200
    assert call("POST", "/start-work", form)[0] == 303
    with sessions() as db:
        site = db.get(Enterprise, 1)
        assert (site.balance, site.workers_count, site.resource_stored) == (0, 0, 14)
        assert db.get(User, 10).gold == 154
        assert db.scalar(select(EnterpriseShift)).status == "completed"
        assert db.scalars(select(EnterpriseEvent.kind)).all() == ["employment"]
        report = db.scalar(select(EnterpriseDailyReport))
        assert (report.produced, report.wages) == ({"singing_resin": 4}, 54)
    assert b"22-11-2026" not in call("GET")[1]
    now = datetime(2026, 11, 22, 22)  # 00:00 in Kyiv, after the November UTC+2 transition.
    status, page = call("GET")
    assert status == 200 and b"22-11-2026" in page
    assert "виплачено 54 золота за роботу".encode() in page
    assert b'<a href="/player_info?id=10">reader</a>.' in page.split(b'id="enterprise-history"', 1)[1]


def test_daily_history_groups_shift_starts_by_local_day(sessions, monkeypatch):
    now = datetime(2026, 11, 22, 20, 30)
    monkeypatch.setattr(enterprise, "utc_now", lambda: now)
    monkeypatch.setattr(enterprises, "utc_now", lambda: now)
    call = site_client(sessions)
    assert call("POST", "/start-work")[0] == 200
    assert call("POST", "/start-work", player="other")[0] == 200
    now += enterprises.SHIFT_DURATION
    assert call("POST", "/start-work")[0] == 200
    now = datetime(2026, 11, 22, 22)
    status, page = call("GET")
    assert status == 200
    history = page.decode().split('id="enterprise-history"', 1)[1]
    assert '<a href="/player_info?id=2">other</a>, <a href="/player_info?id=10">reader</a>(2 рази).' in history


def test_manufacturing_procurement_and_stock_limits(sessions, monkeypatch):
    policy = enterprises.Rules(
        pricing={}, employment={},
        enterprises={1: {"units_per_worker": 6, "inputs_per_unit": {"basalt_bone": 2}}},
    )
    monkeypatch.setattr(enterprises, "rules", lambda: policy)
    now = datetime(2026, 11, 22, 12)
    monkeypatch.setattr(enterprise, "utc_now", lambda: now)
    monkeypatch.setattr(enterprises, "utc_now", lambda: now)
    with sessions.begin() as db:
        site = db.get(Enterprise, 1)
        site.owner_id, site.max_storage = 10, 12
        db.add(Enterprise(id=2, name="Постачальник", resource_type="basalt_bone",
                          resource_stored=10, max_storage=10, item_price=10))
    call = site_client(sessions)
    assert call("POST", "/start-work")[0] == 200
    now += enterprises.SHIFT_DURATION
    assert call("GET")[0] == 200
    with sessions() as db:
        assert db.get(Enterprise, 1).resource_stored == 10
    assert call("POST", "/procure-input", {"supplier_id": 2, "amount": 5}, player="other")[0] == 403
    form = {"supplier_id": 2, "amount": 5, "expected_price": 9, "expected_total": 46,
            "request_key": str(uuid4())}
    assert call("POST", "/procure-input", form)[0] == 303
    assert call("POST", "/procure-input", form)[0] == 303
    assert call("POST", "/start-work")[0] == 200
    now += enterprises.SHIFT_DURATION
    assert call("GET")[0] == 200
    assert call("POST", "/start-work")[0] == 200
    now += enterprises.SHIFT_DURATION
    assert call("GET")[0] == 200
    with sessions() as db:
        site, supplier = db.get(Enterprise, 1), db.get(Enterprise, 2)
        assert (site.resource_stored, site.input_stock, site.balance) == (12, {"basalt_bone": 1}, 864)
        assert (supplier.resource_stored, supplier.balance) == (5, 1045)


def test_purchase_quote_commission_gold_stock_and_concurrent_retry(sessions):
    call = site_client(sessions)
    with sessions.begin() as db:
        site = db.get(Enterprise, 1)
        site.item_price, site.max_storage = 10, 10
        db.get(User, 2).gold = 0
    def form(amount, price=9, total=None):
        return {"amount": amount, "expected_price": price, "expected_total": total or amount * price + 1,
                "request_key": str(uuid4())}
    assert call("POST", "/buy-resources", form(1), player="other")[0] == 400
    assert call("POST", "/buy-resources", form(11))[0] == 409
    status, page = call("POST", "/buy-resources", form(1, price=10))
    assert status == 409 and "Ціна змінилася".encode() in page
    with sessions.begin() as db:
        db.get(User, 2).gold = 100
    barrier = Barrier(2)
    order = form(10)

    def buy(player, fields):
        barrier.wait()
        return call("POST", "/buy-resources", fields, player=player)[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(buy, "reader", order)
        second = executor.submit(buy, "other", form(10))
        outcomes = [first.result(), second.result()]
    assert sorted(outcomes) == [303, 409]
    if outcomes[0] == 303:
        assert call("POST", "/buy-resources", order)[0] == 303
    with sessions() as db:
        site = db.get(Enterprise, 1)
        events = db.scalars(select(EnterpriseEvent)).all()
        assert (site.resource_stored, site.balance, len(events)) == (0, 1090, 1)
        assert events[0].details["fee"] == 1
        report = db.scalar(select(EnterpriseDailyReport))
        assert (report.sold, report.sale_gold) == ({"singing_resin": 10}, 90)
        assert sum(db.get(User, key).gold for key in (10, 2)) == 109
        assert sum(db.get(User, key).singing_resin for key in (10, 2)) == 10


def test_supply_prices_and_transfer_fee():
    assert economy.supply_price(100, 0, 4000, 90, 120) == 120
    assert economy.supply_price(100, 2000, 4000, 90, 120) == 105
    assert economy.supply_price(100, 4000, 4000, 90, 120) == 90
    assert economy.gold_commission(200) == 2
    assert economy.gold_commission(200, direct_transfer=True) == 0


def test_optional_victory_requirement_and_legacy_shift(sessions, monkeypatch):
    from backend.engine.battle_models import Battle, BattleParticipant

    policy = enterprises.Rules(
        pricing={}, employment={"require_victory_between_shifts": True},
        enterprises={1: {"units_per_worker": 1}},
    )
    monkeypatch.setattr(enterprises, "rules", lambda: policy)
    now = datetime(2026, 11, 22, 12)
    monkeypatch.setattr(enterprise, "utc_now", lambda: now)
    monkeypatch.setattr(enterprises, "utc_now", lambda: now)
    with sessions.begin() as db:
        site, worker = db.get(Enterprise, 1), db.get(User, 10)
        site.balance, site.salary, site.workers_count = 970, 30, 1
        worker.workplace = "enterprise_1"
        worker.work_start_time = datetime(2000, 1, 1)
    call = site_client(sessions)
    assert call("GET")[0] == 200
    assert call("POST", "/start-work")[0] == 400
    with sessions.begin() as db:
        assert db.get(Enterprise, 1).balance == 970
        assert db.get(User, 10).gold == 130
        battle = Battle(mode="pve", state={}, status="finished", winner_side=0, finished_at=now)
        db.add(battle)
        db.flush()
        db.add(BattleParticipant(battle_id=battle.id, side=0, user_id=10))
    assert call("POST", "/start-work")[0] == 200


def test_admin_can_edit_enterprises_without_truncating_stock(sessions):
    call = site_client(sessions)
    url = "/admin/enterprises"
    assert call("GET", url)[0] == 403
    with sessions.begin() as db:
        db.get(User, 10).is_admin = True
    status, page = call("GET", url)
    assert status == 200 and b'action="/admin/enterprises/edit/1"' in page
    form = {"name": "Тиха шахта", "sector": "Castle", "resource_type": "singing_resin",
            "production_type": "mine", "salary": 40, "item_price": 10, "max_storage": 9}
    assert call("POST", url + "/edit/1", form, player="other")[0] == 403
    assert call("POST", url + "/edit/1", form)[0] == 409
    form["max_storage"] = 12
    assert call("POST", url + "/edit/1", form)[0] == 303
    with sessions() as db:
        site = db.get(Enterprise, 1)
        assert (site.production_type, site.max_storage, site.resource_stored, site.salary) == ("mine", 12, 10, 40)
