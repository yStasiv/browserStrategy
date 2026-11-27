import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import FastAPI, HTTPException
import pytest
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from backend import database
from backend.models import Item, PlayerResourceBalance, ShopItem, User
from backend.routers import item, shop
from backend.scripts.add_shop_items import ARTIFACTS_FILE, PROJECT_ROOT, add_shop_items
from backend.services.artifact_shop import BONUS_LABELS, buy, offers
from backend.services.hero_equipment import ITEM_SLOTS
from backend.services.resource_balances import resource_owners, resource_quantity
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
        listing = db.scalar(select(ShopItem).order_by(ShopItem.id).limit(1))
        catalog_price, catalog_resources = listing.price, listing.resource_costs
        listing_id = listing.id
        listing.quantity = 4
        listing.price = 1
        owned = Item(name=listing.item_template.name, owner_id=10, item_type=listing.item_template.item_type,
                     image_url="/static/images/items/weapons/legendary_sword.png",
                     durability=7, max_durability=20, stats={"melee_attack": 2})
        db.add(owned)
        db.flush()
        owned_id = owned.id
        db.commit()
        add_shop_items(db, sync_existing=True)
        assert len(db.scalars(select(ShopItem)).all()) == len(json.loads(ARTIFACTS_FILE.read_text()))
        assert (listing.quantity, listing.price) == (4, catalog_price)
        assert listing.resource_costs == catalog_resources
        owned = db.get(Item, owned_id)
        assert (owned.stats, owned.durability, owned.max_durability) == ({"melee_attack": 2}, 7, 20)
        assert owned.image_url == listing.item_template.image_url


def test_catalog_exposes_all_artifacts_and_purchases_use_each_level_and_resource_price(sessions):
    catalog = json.loads(ARTIFACTS_FILE.read_text(encoding="utf-8"))
    names_by_level = {entry["shop_data"]["level"]: entry["name"] for entry in catalog}
    with sessions() as db:
        add_shop_items(db, sync_existing=True)
        player = db.get(User, 10)
        listings = {offer["listing"].item_template.name: offer["listing"] for offer in offers(db, player, False)}
        assert listings.keys() == {entry["name"] for entry in catalog}
        for entry in catalog:
            listing = listings[entry["name"]]
            template = listing.item_template
            category = entry["item_type"]
            image_url = template.image_url
            assert category in ITEM_SLOTS and template.item_type == category
            assert template.description == entry["description"]
            assert template.stats == entry["stats"] and template.stats.keys() <= BONUS_LABELS.keys()
            assert template.durability == template.max_durability == entry["max_durability"]
            assert type(entry["repair_cost"]["gold"]) is int and entry["repair_cost"]["gold"] > 0
            assert image_url == entry["image_url"] and image_url.startswith(f"/static/images/items/{category}/")
            assert (PROJECT_ROOT / "frontend" / image_url.lstrip("/")).is_file()
            assert listing.level_required == entry["shop_data"]["level"]
            assert listing.price == entry["shop_data"]["price"]
            assert listing.resource_costs == entry["shop_data"].get("resources", {})
            assert listing.quantity == entry["shop_data"].get("quantity", -1)

        player.gold = 20000
        player.singing_resin = player.basalt_bone = 1000
        for resource in ("whisper_dust", "pulse_spark", "brand_salt"):
            db.add(PlayerResourceBalance(player_id=player.id, resource_id=resource, quantity=1000))
        db.commit()
        for level, name in names_by_level.items():
            listing = listings[name]
            if level > 1:
                player.level = level - 1
                db.commit()
                assert all(offer["listing"].id != listing.id for offer in offers(db, player, True))
                with pytest.raises(HTTPException, match="Потрібен бойовий рівень"):
                    buy(db, player, listing.id)
                db.rollback()
            player.level = level
            db.commit()
            assert any(offer["listing"].id == listing.id for offer in offers(db, player, True))
            prices = {"gold": listing.price, **listing.resource_costs}
            owners = resource_owners(db, player, prices)
            expected = {key: resource_quantity(owners, key) - amount for key, amount in prices.items()}
            buy(db, player, listing.id)
            db.commit()
            owners = resource_owners(db, player, prices)
            assert {key: resource_quantity(owners, key) for key in prices} == expected
            purchased = db.scalar(select(Item).where(Item.owner_id == player.id, Item.name == name))
            assert purchased.image_url == listing.item_template.image_url
            assert purchased.durability == purchased.max_durability == listing.item_template.max_durability



def test_replace_catalog_removes_obsolete_listings_and_preserves_inventory(sessions):
    with sessions() as db:
        obsolete = ShopItem(item_template=Item(name="Obsolete", item_type="belt"), price=1)
        owned = Item(name="Obsolete", item_type="belt", owner_id=10, durability=3)
        db.add_all([obsolete, owned])
        db.commit()
        owned_id = owned.id
        add_shop_items(db, replace_catalog=True)
        expected = json.loads(ARTIFACTS_FILE.read_text())
        listings = db.scalars(select(ShopItem).order_by(ShopItem.id)).all()
        assert {row.item_template.name for row in listings} == {entry["name"] for entry in expected}
        assert db.get(Item, owned_id).durability == 3
        ids = [row.id for row in listings]
        add_shop_items(db, replace_catalog=True)
        assert db.scalars(select(ShopItem.id).order_by(ShopItem.id)).all() == ids
