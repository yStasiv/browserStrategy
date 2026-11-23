import asyncio
import json

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend import database
from backend.engine.battle_models import Battle, BattleParticipant
from backend.models import Item, User
from backend.routers import inventory
from test_guild import asgi_request, sessions


def test_inventory_renders_stats_and_shared_equipment_and_checks_actions(sessions):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    app.include_router(inventory.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, form=None):
        return asyncio.run(asgi_request(app, method, path, "session_id=reader-session", form=form))

    with sessions.begin() as db:
        player = db.get(User, 10)
        player.gender, player.fraction = "female", "undergroundElves"
        db.add_all([
            Item(id=41, owner_id=10, name="Перстень", item_type="jewelry", stats={"mind": 2, "luck": 1}),
            Item(id=42, owner_id=10, name="Лук", item_type="bow", stats={"melee_attack": 2}),
            Item(id=43, owner_id=10, name="Щит", item_type="shield"),
            Item(id=44, owner_id=10, name="Зламаний пояс", item_type="belt", durability=0, max_durability=10),
            Item(id=45, owner_id=2, name="Чужий пояс", item_type="belt"),
            Item(id=46, owner_id=10, name="Меч", item_type="one_handed_weapon", stats={"melee_attack": 3}),
            Item(id=47, owner_id=10, name="Важкий щит", item_type="shield", level_required=9),
        ])
    status, page = call("GET", "/inventory")
    assert status == 200
    assert page.count(b"data-hero-stat=") == 7
    assert page.count(b'data-hero-slot=') == 11
    assert b"underground_elves_woman_back_model.png" in page
    assert b'data-artifact-tooltip' in page
    assert 'Міцність 0/10'.encode() in page
    assert call("POST", "/inventory/equip/44")[0] == 422
    assert call("POST", "/inventory/destroy/45")[0] == 404
    assert call("POST", "/inventory/unequip/41")[0] == 409
    assert call("POST", "/inventory/equip/41", {"selected_slot": "acc_4", "return_to_inventory": "true"})[0] == 303
    assert call("POST", "/inventory/equip/42?slot=main_hand")[0] == 422
    assert call("POST", "/inventory/equip/46")[0] == 200
    assert call("POST", "/inventory/equip/42")[0] == 200
    assert call("POST", "/inventory/equip/43")[0] == 409
    status, stats = call("GET", "/inventory/stats")
    assert status == 200
    values = json.loads(stats)
    assert (values["mind"], values["luck"], values["melee_attack"]) == (2, 1, 5)
    equipped_page = call("GET", "/inventory")[1]
    assert b'action="/inventory/unequip/41"' in equipped_page
    assert b'type="submit" form="inventory-unequip-acc_4" data-artifact-trigger' in equipped_page
    status, body = call("POST", "/inventory/equip/47", {"replace": "true"})
    assert status == 422 and json.loads(body)["detail"]["code"] == "artifact_level"
    with sessions() as db:
        assert db.get(User, 10).equipped_items.left_hand_id == 42
    assert call("POST", "/inventory/equip/43", {"replace": "true"})[0] == 200
    assert call("POST", "/inventory/destroy/42", {"return_to_inventory": "true"})[0] == 303
    assert call("POST", "/inventory/unequip/41")[0] == 200
    with sessions.begin() as db:
        player = db.get(User, 10)
        assert (player.melee_attack, player.mind) == (3, 0)
        assert player.equipped_items.right_hand_id == 46
        assert player.equipped_items.jewelry_4_id is None
        assert player.equipped_items.left_hand_id == 43
        assert db.get(Item, 42) is None
        battle = Battle(mode="pve", status="deployment", state={})
        db.add(battle)
        db.flush()
        db.add(BattleParticipant(battle_id=battle.id, side=0, user_id=10))
    assert call("POST", "/inventory/unequip/43")[0] == 409
