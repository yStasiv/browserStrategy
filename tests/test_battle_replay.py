import asyncio
import json

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import database, db_base
from backend.engine import battle_api, battle_service, create_battle
from backend.engine.actions import Defend, action_to_dict
from backend.engine.ai import choose_action
from backend.engine.battle_experience import earned_experience
from backend.engine.battle_models import ArmySlot, Battle, BattleParticipant
from backend.engine.events import reconstruct
from backend.engine.flow import play_turn
from backend.engine.setup import FieldRules
from backend.routers import admin
from backend.models import EquippedItems, Item, RewardTransaction, User
from backend.config import SYSTEM_PLAYER_ID
from test_guild import asgi_request


def test_completed_battle_replays_through_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'battle.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    sessions = sessionmaker(engine, autoflush=False)
    with sessions.begin() as db:
        db.add_all([
            User(id=10, username="fighter", level=4, gold=100, experience=0, physical_defense=2, session_id="fighter-token"),
            User(id=11, username="outsider", session_id="outsider-token", is_admin=True),
        ])
        db.flush()
        db.add_all([
            Item(id=201, owner_id=10, item_type="helmet", durability=1, max_durability=10,
                 is_equipped=True, stats={"physical_defense": 2}),
            Item(id=202, owner_id=10, item_type="helmet", durability=5, max_durability=10),
        ])
        db.flush()
        db.add(EquippedItems(user_id=10, helmet_id=201))
        db.add_all([
            ArmySlot(user_id=10, slot=slot, unit_key=key, count=count)
            for slot, (key, count) in enumerate((("peasant", 20), ("archer", 10), ("swordsman", 5)))
        ])
    monkeypatch.setattr(battle_service.secrets, "randbits", lambda _: 42)

    app = FastAPI()
    app.include_router(battle_api.router)
    app.include_router(admin.router)

    def get_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[database.get_db] = get_db

    def call(method, path, payload=None, token="fighter-token"):
        status, body = asyncio.run(asgi_request(
            app, method, "/api/battles" + path, f"session_id={token}", payload=payload
        ))
        return status, json.loads(body)

    status, battle = call("POST", "/pve", {"scenario": "training"})
    assert status == 200
    root = f"/{battle['id']}"
    assert call("GET", root + "/replay")[0] == 409
    admin_replay_path = f"/admin/api/stats/replay/{battle['id']}"
    assert asyncio.run(asgi_request(app, "GET", admin_replay_path, "session_id=outsider-token"))[0] == 409
    assert call("GET", root + "/events", token="outsider-token")[0] == 403
    assert battle["status"] == "deployment"
    obstacles = battle["state"]["obstacles"]
    assert obstacles and battle["state"]["obstacle_kind"] == "rock"
    active = call("GET", "/active")[1]
    assert active["id"] == battle["id"] and active["state"]["obstacles"] == obstacles
    assert call("POST", root + "/auto", {"version": battle["version"]})[0] == 409
    assert battle["deployment"]["remaining"] == 0 and battle["deployment"]["can_begin"]
    initially_placed = battle["state"]["placed_stack_ids"]
    assert len(initially_placed) == 3
    auto_path = root + "/deployment/auto"
    status, battle = call("POST", auto_path, {"version": battle["version"]})
    assert status == 200 and not battle["deployment"]["restored_previous"]
    assert battle["state"]["placed_stack_ids"] == initially_placed
    placement = {"version": battle["version"], "stack_id": "s0_0", "x": 1, "y": 1}
    assert call("POST", root + "/deployment", dict(placement, x=7))[0] == 400
    assert call("POST", root + "/deployment", dict(placement, stack_id="s1_0"))[0] == 400
    split_path = root + "/deployment/split"
    split = {"version": battle["version"], "stack_id": "s0_0", "count": 3}
    assert call("POST", split_path, dict(split, count=20))[0] == 400
    status, battle = call("POST", split_path, split)
    assert status == 200
    assert battle["state"]["stacks"]["s0_0"]["count"] == 17
    child = battle["state"]["stacks"]["s0_3"]
    assert (child["count"], child["x"], child["y"]) == (3, -1, -1)
    assert battle["state"]["placed_stack_ids"] == initially_placed
    assert "s1_0" in battle["state"]["stacks"]
    assert battle["deployment"]["remaining"] == 1
    assert call("POST", split_path, split)[0] == 409

    merge_path = root + "/deployment/merge"
    merge = {"version": battle["version"], "source_id": "s0_3", "target_id": "s0_0"}
    for invalid in ("s0_3", "s0_1", "s1_0"):
        assert call("POST", merge_path, dict(merge, target_id=invalid))[0] == 400
    original_position = tuple(battle["state"]["stacks"]["s0_0"][key] for key in ("x", "y"))
    status, battle = call("POST", merge_path, merge)
    assert status == 200
    merged = battle["state"]["stacks"]["s0_0"]
    assert (merged["count"], merged["initial_count"]) == (20, 20)
    assert (merged["x"], merged["y"]) == original_position
    assert "s0_3" not in battle["state"]["stacks"]
    assert battle["deployment"]["remaining"] == 0
    assert call("POST", merge_path, merge)[0] == 409
    assert call("GET", "/active")[1]["state"] == battle["state"]

    assert battle["deployment"]["can_begin"]
    status, battle = call("POST", split_path, dict(split, version=battle["version"]))
    assert status == 200 and battle["deployment"]["remaining"] == 1
    assert not battle["deployment"]["can_begin"]
    assert call("POST", root + "/begin", {"version": battle["version"]})[0] == 409
    assert call("GET", "/active")[1]["state"]["stacks"]["s0_3"]["x"] == -1
    status, battle = call("POST", root + "/deployment", dict(placement, version=battle["version"], stack_id="s0_3"))
    assert status == 200 and battle["deployment"]["can_begin"]

    begin_payload = {"version": battle["version"]}
    status, battle = call("POST", root + "/begin", begin_payload)
    assert status == 200
    assert call("POST", root + "/begin", begin_payload)[0] == 409
    assert call("POST", merge_path, dict(merge, version=battle["version"]))[0] == 409
    baseline = call("GET", root + "/events")[1]
    assert baseline["initial_state"]["stacks"]["s0_3"]["count"] == 3
    assert baseline["initial_state"]["seq"] == 0
    assert baseline["initial_state"]["stacks"]["s0_0"]["initial_count"] == 17
    assert baseline["initial_state"]["stacks"]["s0_3"]["initial_count"] == 3
    assert baseline["initial_state"]["obstacles"] == battle["state"]["obstacles"] == obstacles
    assert baseline["events"][0]["payload"]["obstacles"] == obstacles
    assert baseline["events"][0]["payload"]["obstacle_kind"] == "rock"
    assert baseline["initial_state"]["initial_ready_at"]["hero_0"] == baseline["initial_state"]["heroes"]["hero_0"]["ready"]
    assert baseline["events"][0]["payload"]["initial_ready_at"] == baseline["initial_state"]["initial_ready_at"]

    auto_payload = {"version": battle["version"]}
    assert call("POST", root + "/auto", auto_payload, token="outsider-token")[0] == 403
    status, battle = call("POST", root + "/auto", auto_payload)
    assert status == 200
    assert call("POST", root + "/auto", auto_payload)[0] == 409

    for _ in range(100):
        if battle["status"] == "finished":
            break
        state = battle_service.BattleState.from_dict(battle["state"])
        payload = {"action": action_to_dict(choose_action(state)), "version": battle["version"]}
        status, battle = call("POST", root + "/actions", payload)
        assert status == 200
        if battle["status"] == "active":
            assert call("POST", root + "/actions", payload)[0] == 409
    assert battle["status"] == "finished"
    assert battle["winner_side"] == 0

    with sessions() as db:
        player = db.get(User, 10)
        balances = player.gold, player.experience
        assert battle["reward"] == {"gold": player.gold - 100, "experience": player.experience}
        assert call("GET", root)[1]["reward"] == battle["reward"]
        assert 132 <= player.gold <= 398
        record = db.get(Battle, battle["id"])
        assert (db.get(Item, 201).durability, db.get(Item, 202).durability) == (0, 5)
        assert not db.get(Item, 201).is_equipped
        assert db.get(Item, 201).owner_id == player.id
        assert player.equipped_items.helmet_id is None and player.physical_defense == 0
        state_type = battle_service.BattleState
        assert player.experience == earned_experience(
            state_type.from_dict(record.initial_state), state_type.from_dict(record.state), 0,
        ) > 0
        assert record.rewarded
    status, replay = call("GET", root + "/replay")
    assert status == 200
    assert call("GET", root + "/replay", token="outsider-token")[0] == 403
    assert asyncio.run(asgi_request(app, "GET", admin_replay_path, "session_id=fighter-token"))[0] == 403
    status, admin_payload = asyncio.run(asgi_request(app, "GET", admin_replay_path, "session_id=outsider-token"))
    assert status == 200
    assert json.loads(admin_payload)["events"] == replay["events"]
    assert replay["schema_version"] == 1
    assert replay["reward"] == battle["reward"]
    assert replay["result"] == battle["result"]
    damage = {0: {}, 1: {}}
    hero_damage = {hero["owner"]: 0 for hero in replay["initial_state"]["heroes"].values()}
    for event in replay["events"]:
        hero_hit = event.get("hero_damage")
        if hero_hit:
            assert event["type"] == "DAMAGE_APPLIED"
            assert hero_hit["amount"] == event["payload"]["hp_before"] - event["payload"]["hp_after"]
            assert event["actor_id"] in replay["initial_state"]["heroes"]
            hero_damage[hero_hit["side"]] += hero_hit["amount"]
        hit = event.get("creature_damage")
        if hit:
            assert hit["amount"] == event["payload"]["hp_before"] - event["payload"]["hp_after"]
            assert not event["actor_id"].startswith("hero_")
            side = damage[hit["side"]]
            side[hit["unit"]] = side.get(hit["unit"], 0) + hit["amount"]
    assert any(damage.values())
    assert hero_damage[0] > 0
    for side in battle["creature_damage"]["sides"]:
        assert {entry["unit"]: entry["amount"] for entry in side["creatures"]} == damage[side["side"]]
        assert side["total"] == sum(damage[side["side"]].values())
        assert side["hero_total"] == hero_damage.get(side["side"])
    assert call("GET", root)[1]["creature_damage"] == battle["creature_damage"]
    result = battle["result"]
    assert result["battle_id"] == battle["id"] and result["winner_side"] == battle["winner_side"]
    assert result["replay_available"]
    sides = {side["side"]: side["participants"] for side in result["sides"]}
    assert sides[0][0]["name"] == "fighter"
    assert {entry["type"]: entry["amount"] for entry in sides[0][0]["rewards"]} == {
        key: amount for key, amount in battle["reward"].items() if amount
    }
    assert sides[1][0]["name"] and not sides[1][0]["rewards"]
    assert reconstruct(replay["initial_state"], replay["events"]) == replay["final_state"] == battle["state"]
    assert [event["sequence"] for event in replay["events"]] == sorted(
        {event["sequence"] for event in replay["events"]}
    )
    assert {"UNIT_MOVED", "DAMAGE_APPLIED", "UNIT_KILLED", "BATTLE_FINISHED"} <= {
        event["type"] for event in replay["events"]
    }
    assert call("GET", root + "/replay")[1] == replay
    assert call("POST", root + "/surrender", {"version": battle["version"]})[0] == 400
    with sessions() as db:
        assert db.query(RewardTransaction).filter_by(source="battle_v1", source_key=str(battle["id"])).count() == 1
    assert call("POST", root + "/actions", payload)[0] == 400
    assert call("GET", "/history")[1] == [{"id": battle["id"], "available": True}]
    with sessions() as db:
        player = db.get(User, 10)
        assert (player.gold, player.experience) == balances
        assert db.get(Item, 201).durability == 0


    status, next_battle = call("POST", "/pve", {"scenario": "training"})
    assert status == 200 and next_battle["deployment"]["can_begin"]
    assert "s0_3" not in next_battle["state"]["stacks"]
    status, restored = call("POST", f"/{next_battle['id']}/deployment/auto", {
        "version": next_battle["version"],
    })
    assert status == 200 and restored["deployment"]["restored_previous"]
    assert restored["status"] == "deployment" and restored["deployment"]["can_begin"]

    def formation(state):
        return {(stack["unit"], stack["count"], stack["x"], stack["y"])
                for stack in state["stacks"].values() if stack["owner"] == 0}

    assert formation(restored["state"]) == formation(replay["initial_state"])
    assert call("GET", "/active")[1]["state"] == restored["state"]


def test_draw_result_reads_extensible_ledger_metadata(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'draw.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    sessions = sessionmaker(engine)
    state = create_battle([("archer", 1)], [("peasant", 1)], 42)
    state.status, state.active_id = "finished", None
    with sessions.begin() as db:
        db.add_all([
            User(id=10, username="Ада"), User(id=11, username="Лада"),
            Battle(id=50, mode="pvp", status="finished", state=state.to_dict()),
        ])
        db.flush()
        db.add_all([
            BattleParticipant(battle_id=50, user_id=10, side=0),
            BattleParticipant(battle_id=50, user_id=11, side=1),
            RewardTransaction(
                issuer_id=SYSTEM_PLAYER_ID, recipient_id=10, source="battle_v1", source_key="50",
                gold=0, wood=0, stone=0, created_at=db.get(Battle, 50).created_at,
                reward_entries=[
                    {"type": "experience", "amount": 12},
                    {"type": "achievement", "label": "Досягнення", "value": "Суперник гідний"},
                ],
            ),
        ])
    with sessions() as db:
        payload = battle_service.get_battle_view(db, db.get(User, 10), 50)
        assert payload["reward"] == {"experience": 12, "gold": 0}
        result = payload["result"]
        assert result["winner_side"] is None and result["replay_available"] is False
        assert result["sides"][0]["participants"][0]["rewards"][1] == {
            "type": "achievement", "label": "Досягнення", "value": "Суперник гідний",
        }
        assert result["sides"][1]["participants"] == [{"name": "Лада", "rewards": []}]


def test_defend_expires_at_own_turn_and_is_recorded():
    initial = create_battle([("swordsman", 2)], [("swordsman", 2)], seed=1)
    state, first = play_turn(initial, initial.active().owner, Defend())
    assert any(event["type"] == "STATUS_APPLIED" for event in first[0].replay_events)
    assert state.stacks[initial.active_id].defending
    state, second = play_turn(state, state.active().owner, Defend())
    assert any(event["type"] == "STATUS_EXPIRED" and event["actor_id"] == initial.active_id
               for event in second[0].replay_events)
    assert reconstruct(initial.to_dict(), first[0].replay_events + second[0].replay_events) == state.to_dict()


def test_explicit_field_dimensions_preserve_default_slot_rules():
    options = FieldRules(width=12, height=10, max_slots=5)
    state = create_battle([("archer", 2)], [("ogre", 2)], seed=1, configuration=options)
    assert (state.width, state.height) == (12, 10)
    for event in play_turn(state, state.active().owner, choose_action(state))[1][0].replay_events:
        if event["type"] == "UNIT_MOVED":
            assert event["payload"]["from"] not in event["payload"]["path"]


def test_legacy_active_battle_replays_from_checkpoint(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    sessions = sessionmaker(engine, autoflush=False)
    with sessions.begin() as db:
        db.add(User(id=10, username="legacy", level=4, gold=0, experience=0))
        db.flush()
        db.add(ArmySlot(user_id=10, slot=0, unit_key="archer", count=10))
    with sessions() as db:
        player = db.get(User, 10)
        battle = battle_service.start_pve(db, player, "training")
        archer = battle["state"]["stacks"]["s0_0"]
        battle = battle_service.update_deployment(
            db, player, battle["id"], battle["version"], (archer["id"], archer["x"], archer["y"])
        )
        battle = battle_service.update_deployment(db, player, battle["id"], battle["version"])
        old_state = battle["state"]
        if old_state["seq"] == 0:
            action = action_to_dict(choose_action(battle_service.BattleState.from_dict(old_state)))
            battle = battle_service.submit_action(db, player, battle["id"], action, battle["version"])
            old_state = battle["state"]
        row = db.get(Battle, battle["id"])
        row.initial_state = None
        row.replay_schema_version = None
        db.commit()
        battle_service.surrender_battle(db, player, battle["id"], battle["version"])
        replay = battle_service.battle_events(db, player, battle["id"], finished_only=True)
        assert replay["partial"]
        assert replay["events"][0]["type"] == "REPLAY_CHECKPOINT"
        assert replay["initial_state"] == old_state
        assert reconstruct(old_state, replay["events"]) == replay["final_state"]


def test_experience_depends_on_enemy_hp_survivors_and_outcome():
    initial = create_battle([("peasant", 20)], [("goblin", 80)], seed=1)
    state_type = battle_service.BattleState
    final = state_type.from_dict(initial.to_dict())
    final.winner = 0
    assert earned_experience(initial, final, 0) == 100
    final.stacks["s0_0"].count = 10
    assert earned_experience(initial, final, 0) == 75
    final.winner = None
    assert earned_experience(initial, final, 0) == 45
    final.winner = 1
    assert earned_experience(initial, final, 0) == 18
    final.surrendered = 0
    assert earned_experience(initial, final, 0) == 0


def test_pvp_deployment_hides_other_players_until_start(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'pvp.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    sessions = sessionmaker(engine, autoflush=False)
    with sessions.begin() as db:
        db.add_all([User(id=10, username="left"), User(id=11, username="right")])
        db.flush()
        state = create_battle([("archer", 4)], [("swordsman", 7)], seed=43, mode="pvp")
        state.status = "deployment"
        state.active_id = None
        battle = Battle(mode="pvp", level=1, status="deployment", state=state.to_dict(), version=0)
        db.add(battle)
        db.flush()
        battle_id = battle.id
        db.add_all([BattleParticipant(battle_id=battle_id, user_id=10, side=0),
                    BattleParticipant(battle_id=battle_id, user_id=11, side=1)])

    with sessions() as db:
        left, right = db.get(User, 10), db.get(User, 11)
        placed = battle_service.update_deployment(db, left, battle_id, 0, ("s0_0", 1, 2))
        assert set(placed["state"]["stacks"]) == {"s0_0"}
        assert placed["state"]["placed_stack_ids"] == ["s0_0"]
        opponent = battle_service.get_battle_view(db, right, battle_id)
        assert set(opponent["state"]["stacks"]) == {"s1_0"}
        assert opponent["state"]["placed_stack_ids"] == []
        assert "initial_ready_at" not in opponent["state"]

        assert not placed["deployment"]["can_begin"] and not opponent["deployment"]["can_begin"]
        enemy_stack = opponent["state"]["stacks"]["s1_0"]
        ready = battle_service.update_deployment(db, right, battle_id, 1, (
            enemy_stack["id"], enemy_stack["x"], enemy_stack["y"],
        ))
        assert ready["deployment"]["can_begin"]
        started = battle_service.update_deployment(db, right, battle_id, ready["version"])
        assert started["status"] == "active"
        assert set(started["state"]["stacks"]) == {"s0_0", "s1_0"}
        assert started["state"]["stacks"]["s0_0"]["x"] == 1
