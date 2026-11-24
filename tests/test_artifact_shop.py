import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend import database
from backend.models import Item, PlayerResourceBalance, ShopItem, User
from backend.routers import item, shop
from backend.scripts.add_shop_items import add_shop_items
from test_guild import asgi_request, sessions


def test_shop_charges_all_resources_and_keeps_finite_stock_atomic(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(shop.router)
    app.include_router(item.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, player="reader"):
        return asyncio.run(asgi_request(app, method, path, f"session_id={player}-session"))

    with sessions.begin() as db:
        template = Item(name="Тестовий артефакт", item_type="helmet",
                        stats={"physical_defense": 2, "stamina": 1}, durability=5, max_durability=12)
        listing = ShopItem(item_template=template, price=50, level_required=2, quantity=1,
                           resource_costs={"basalt_bone": 2, "pulse_spark": 1})
        db.add(listing)
        db.flush()
        listing_id, item_id = listing.id, template.id
        for player_id in (2, 10):
            db.get(User, player_id).basalt_bone = 3
    path = f"/shop/buy/{listing_id}"
    status, shop_page = call("GET", "/shop")
    assert status == 200
    assert f"/art_info?id={item_id}".encode() in shop_page
    assert "Пульс-іскра".encode() in shop_page and "Витривалість".encode() not in shop_page
    assert b"/static/images/hero_stats/defense.png" in shop_page
    assert b"/static/images/items/background_icons/bow.png" in shop_page
    assert "Зброя й луки".encode() not in shop_page
    assert f"/art_info?id={item_id}".encode() in call("GET", "/shop?category=helmets&my_level=1")[1]
    assert f"/art_info?id={item_id}".encode() not in call("GET", "/shop?category=belts")[1]
    assert call("POST", path)[0] == 400
    with sessions.begin() as db:
        assert db.get(User, 10).gold == 100
        assert db.get(User, 10).basalt_bone == 3
        db.get(User, 2).level = 2
        db.add_all([PlayerResourceBalance(player_id=player_id, resource_id="pulse_spark", quantity=1)
                    for player_id in (2, 10)])
    gate = Barrier(2)

    def buy(player):
        gate.wait(timeout=5)
        return call("POST", path, player)[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(buy, ("reader", "other"))) == [200, 400]
    with sessions() as db:
        purchased = db.scalar(select(Item).where(Item.owner_id.is_not(None)))
        assert (purchased.stats, purchased.durability, purchased.max_durability) == ({"physical_defense": 2}, 12, 12)
        owner = db.get(User, purchased.owner_id)
        assert (owner.gold, owner.basalt_bone) == (50, 1)
        assert db.get(PlayerResourceBalance, (owner.id, "pulse_spark")).quantity == 0
        assert db.get(ShopItem, listing_id).quantity == 0


def test_sync_catalog_updates_templates_without_resetting_stock_or_owned_items(sessions):
    with sessions() as db:
        add_shop_items(db)
        listing = db.scalar(select(ShopItem).where(ShopItem.quantity == 5))
        listing_id = listing.id
        listing.quantity = 4
        listing.price = 1
        owned = Item(name=listing.item_template.name, owner_id=10, stats={"melee_attack": 2})
        db.add(owned)
        db.flush()
        owned_id = owned.id
        db.commit()
        add_shop_items(db, sync_existing=True)
        assert len(db.scalars(select(ShopItem)).all()) == 16
        assert (listing.quantity, listing.price) == (4, 1600)
        assert listing.resource_costs == {"basalt_bone": 40, "pulse_spark": 16}
        assert db.get(Item, owned_id).stats == {"melee_attack": 2}
