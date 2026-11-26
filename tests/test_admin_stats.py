import asyncio
import json
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend import database
from backend.config import SYSTEM_PLAYER_ID
from backend.engine.battle_models import Battle, BattleAction, BattleParticipant
from backend.guild_models import ActivityGuildProgress
from backend.models import Item, RepairJob, RewardTransaction, ShopItem, User
from backend.routers import admin
from backend.services import admin_stats, artifact_shop, forge_repairs, gameplay_events, hero_equipment
from test_guild import asgi_request, sessions


def test_admin_statistics_access(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(admin.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def get(path, cookie=""):
        return asyncio.run(asgi_request(app, "GET", path, cookie))

    with sessions.begin() as db:
        db.get(User, 10).is_admin = True

    for path in ("/admin/stats", "/admin/api/stats", "/admin/api/stats/replay/1"):
        assert get(path)[0] in (401, 403)
        assert get(path, "session_id=other-session")[0] in (401, 403)
    assert get("/admin/stats", "session_id=reader-session")[0] == 200
    for period, granularity in (("24h", "hourly"), ("7d", "daily"), ("30d", "daily"), ("all", "daily")):
        status, body = get(f"/admin/api/stats?period={period}", "session_id=reader-session")
        assert status == 200
        data = json.loads(body)
        assert data["series"]["granularity"] == granularity
        for section in ("battles", "economy"):
            timestamps = [row["bucket"] for row in data["series"][section]]
            assert timestamps and timestamps == sorted(set(timestamps))
    assert get("/admin/api/stats?period=yesterday", "session_id=reader-session")[0] == 422
    assert get("/admin/api/stats/replay/1", "session_id=reader-session")[0] == 404


@pytest.fixture
def history(sessions):
    now = datetime(2026, 11, 25, 14, 30)
    snapshots = [
        (timedelta(hours=3), 0, None, 18),
        (timedelta(days=3), 1, None, 30),
        (timedelta(days=15), None, None, 600),
        (timedelta(days=50), 1, 0, 20),
        (timedelta(hours=-1), 0, None, 5),
    ]
    with sessions.begin() as db:
        db.get(User, 10).last_seen_at = now - timedelta(hours=1)
        db.get(User, 2).last_seen_at = now - timedelta(days=10)
        db.add(ActivityGuildProgress(player_id=10, guild="metalworkers", points=12))
        for index, (age, winner, surrendered, actions) in enumerate(snapshots, 1):
            moment = now - age
            battle = Battle(id=index, mode="pve", status="finished", winner_side=winner, created_at=moment,
                            finished_at=moment, state={"seq": actions, "surrendered": surrendered,
                                                       "hunt_key": "goblin", "hunt_level": index},
                            initial_state={"summoning": {"0": {"school_level": 3}}}, replay_schema_version=1)
            db.add(battle)
            db.flush()
            db.add(BattleParticipant(battle_id=index, side=0, user_id=10))
            db.add(RewardTransaction(issuer_id=SYSTEM_PLAYER_ID, recipient_id=10, source="battle_v1",
                                     source_key=str(index), created_at=moment, gold=10, wood=2, stone=3,
                                     reward_entries=[{"type": "experience", "amount": 50},
                                                     {"type": "pulse_spark", "amount": 4}]))
            gameplay_events.record(db, "shop_purchase", occurred_at=moment, name="Тестовий пояс", item_type="belt",
                                   level=4, costs={"gold": 11, "basalt_bone": 2})
            gameplay_events.record(db, "repair_started", occurred_at=moment, gold=8, succeeded=False)
            gameplay_events.record(db, "repair_refund", occurred_at=moment, gold=4)
        db.add_all([
            Battle(mode="pve", status="deployment", state={}),
            Battle(mode="pvp", status="active", state={}),
            BattleAction(battle_id=1, seq=0, side=0, action={}, events=[], replay_events=[
                {"type": "LUCK_ROLLED", "payload": {"stat": 1, "outcome": "none", "streak_before": 1}},
                {"type": "LUCK_ROLLED", "payload": {"stat": 1, "outcome": "positive", "streak_before": 2}},
                {"type": "MORALE_ROLLED", "payload": {"stat": -2, "outcome": "negative", "streak_before": 1}},
                {"type": "ELEMENTAL_SUMMONED", "payload": {"spell": "earth"}},
            ]),
        ])
    return now


@pytest.mark.parametrize(("period", "total", "active", "buckets"), [
    ("24h", 1, 1, 25), ("7d", 2, 1, 8), ("30d", 3, 2, 31), ("all", 4, 2, 51),
])
def test_aggregates_and_economy_and_battle_series_agree(sessions, history, period, total, active, buckets):
    with sessions() as db:
        data = admin_stats.dashboard(db, period, limit=1, now=history)
    assert data["combat"]["total"] == total
    assert data["combat"]["avg_actions"] == round(sum([18, 30, 600, 20][:total]) / total, 2)
    assert data["combat"]["draw_cap"] == int(total >= 3)
    assert data["hunting"][0]["difficulty"] == {level: 1 for level in range(1, total + 1)}
    assert (data["hunting"][0]["avg_gold"], data["hunting"][0]["avg_xp"]) == (10, 50)
    assert data["effects"]["rolls"][0]["rate"] == 50
    assert data["effects"]["rolls"][0]["avg_streak"] == 2
    assert data["effects"]["rolls"][3]["rate"] == 100
    assert data["effects"]["summons"] == {"3": 1}
    assert data["shop"]["total"] == data["shop"]["categories"]["belt"] == data["shop"]["levels"][4] == total
    assert data["shop"]["top"][0]["count"] == total
    assert data["shop"]["bottom"][0]["count"] == 0
    assert data["economy"]["repairs"] == {"attempts": total, "failures": total, "failure_rate": 100,
                                          "items_broken": 0, "avg_guild_points": 12, "max_guild_points": 12}
    assert data["players"] == {"registered": 2, "active": active, "levels": {1: 1, 8: 1},
                               "sessions": {"active": 1, "deployment": 1}}
    assert len(data["replays"]) == 1 and data["replays"][0]["replay_url"] == "/battle?replay=1&admin_replay=1"
    series = data["series"]
    assert series["granularity"] == ("hourly" if period == "24h" else "daily")
    for rows in (series["battles"], series["economy"]):
        stamps = [row["bucket"] for row in rows]
        assert len(stamps) == buckets and stamps == sorted(set(stamps))
    assert sum(row["total"] for row in series["battles"]) == total
    for index, key in enumerate(admin_stats.OUTCOMES):
        assert sum(row[key] for row in series["battles"]) == data["combat"]["outcomes"][key]["count"] == int(index < total)
    for key, expected in {"earned": 10, "spent": 19, "shop": 11, "repairs": 8, "refunded": 4}.items():
        assert sum(row[key]["gold"] for row in series["economy"]) == data["economy"]["resources"][key]["gold"] == expected * total
    assert data["economy"]["resources"]["earned"]["pulse_spark"] == 4 * total
    assert sum(row["value"] for row in series["breakdowns"]["categories"]) == total
    assert sum(row["value"] for row in series["breakdowns"]["hero_levels"]) == 2


def test_catalog_diagnostics(tmp_path):
    root = tmp_path / "items"
    (root / "belt").mkdir(parents=True)
    (root / "belt" / "valid.png").touch()
    good = {"name": "Пояс", "description": "Опис", "item_type": "belt", "stats": {"luck": 1},
            "image_url": "/static/images/items/belt/valid.png", "durability": 3, "max_durability": 3,
            "shop_data": {"price": 20, "level": 1}, "repair_cost": {"gold": 3}}
    catalog = tmp_path / "artifacts.json"
    catalog.write_text(json.dumps([good]))
    assert admin_stats.catalog_integrity(catalog, root)[0] == {"checked": 1, "ok": True, "issues": []}
    missing = dict(good, name="Без зображення", image_url="/static/images/items/belt/missing.png")
    catalog.write_text(json.dumps([good, missing, dict(good, name="Зламана схема", durability=5)]))
    report, _ = admin_stats.catalog_integrity(catalog, root)
    assert report["checked"] == 3 and not report["ok"]
    assert report["issues"][0]["image_url"] == missing["image_url"]
    assert report["issues"][1]["errors"] == ["Некоректна міцність."]


def test_shop_repairs_and_breakage_feed_statistics(sessions, monkeypatch):
    start = datetime(2026, 11, 25, 12)
    with sessions.begin() as db:
        hero = db.get(User, 10)
        hero.gold, hero.basalt_bone = 500, 5
        listing = ShopItem(item_template=Item(name="Пояс", item_type="belt", durability=12, max_durability=12),
                           price=20, quantity=2, level_required=1, resource_costs={"basalt_bone": 2})
        db.add(listing)
        db.flush()
        artifact_shop.buy(db, hero, listing.id)
        db.flush()
        item = db.scalar(select(Item).where(Item.owner_id == hero.id))
        item.durability = 1
        hero_equipment.wear_battle_equipment(db, hero, [item.id])
        db.flush()
        monkeypatch.setattr(forge_repairs, "success_chance", lambda *_: 20)
        monkeypatch.setattr(forge_repairs.secrets, "randbelow", lambda _: 99)
        db.add(ActivityGuildProgress(player_id=hero.id, guild="metalworking:armor", points=0, level=1))
        forge_repairs.start(db, hero, item, "armor", 1, 30, start, True)
        db.flush()
        job = db.get(RepairJob, hero.id)
        assert not forge_repairs.claim(db, hero, job.token, job.ready_at)[0]
    with sessions() as db:
        data = admin_stats.dashboard(db, "all", now=max(datetime.utcnow(), start + timedelta(days=1)))
        flow = data["economy"]["resources"]
        assert (flow["shop"]["gold"], flow["shop"]["basalt_bone"], flow["repairs"]["gold"], flow["refunded"]["gold"]) == (20, 2, 30, 15)
        assert data["economy"]["repairs"]["items_broken"] == data["economy"]["repairs"]["failures"] == 1
