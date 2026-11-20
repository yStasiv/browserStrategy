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
from backend.engine.battle_models import Battle
from backend.engine.events import reconstruct
from backend.engine.flow import play_turn
from backend.engine.setup import FieldRules
from backend.models import User
from test_guild import asgi_request


def test_completed_battle_replays_through_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'battle.db'}")
    monkeypatch.setattr(db_base, "engine", engine)
    command.upgrade(Config("alembic.ini"), "head")
    sessions = sessionmaker(engine, autoflush=False)
    with sessions.begin() as db:
        db.add_all([
            User(id=10, username="fighter", level=4, gold=100, experience=0, session_id="fighter-token"),
            User(id=11, username="outsider", session_id="outsider-token"),
        ])
    monkeypatch.setattr(battle_service.secrets, "randbits", lambda _: 42)

    app = FastAPI()
    app.include_router(battle_api.router)

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
    assert call("GET", root + "/events", token="outsider-token")[0] == 403
    assert battle["status"] == "deployment"
    assert call("GET", "/active")[1]["id"] == battle["id"]
    assert call("POST", root + "/auto", {"version": battle["version"]})[0] == 409
    placement = {"version": battle["version"], "stack_id": "s0_0", "x": 1, "y": 1, "split_count": 3}
    assert call("POST", root + "/deployment", dict(placement, x=7))[0] == 400
    assert call("POST", root + "/deployment", dict(placement, stack_id="s1_0"))[0] == 400
    status, battle = call("POST", root + "/deployment", placement)
    assert status == 200
    assert battle["state"]["stacks"]["s0_0"]["count"] == 17
    assert battle["state"]["stacks"]["s0_3"]["count"] == 3
    assert call("POST", root + "/deployment", placement)[0] == 409
    begin_payload = {"version": battle["version"]}
    status, battle = call("POST", root + "/begin", begin_payload)
    assert status == 200
    assert call("POST", root + "/begin", begin_payload)[0] == 409
    baseline = call("GET", root + "/events")[1]
    assert baseline["initial_state"]["stacks"]["s0_3"]["count"] == 3
    assert baseline["initial_state"]["seq"] == 0

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
        assert player.experience == 50
        assert db.get(Battle, battle["id"]).rewarded
    status, replay = call("GET", root + "/replay")
    assert status == 200
    assert replay["schema_version"] == 1
    assert replay["reward"] == battle["reward"]
    assert reconstruct(replay["initial_state"], replay["events"]) == replay["final_state"] == battle["state"]
    assert [event["sequence"] for event in replay["events"]] == sorted(
        {event["sequence"] for event in replay["events"]}
    )
    assert {"UNIT_MOVED", "DAMAGE_APPLIED", "UNIT_KILLED", "BATTLE_FINISHED"} <= {
        event["type"] for event in replay["events"]
    }
    assert call("GET", root + "/replay")[1] == replay
    assert call("POST", root + "/actions", payload)[0] == 400
    assert call("GET", "/history")[1] == [{"id": battle["id"], "available": True}]
    with sessions() as db:
        player = db.get(User, 10)
        assert (player.gold, player.experience) == balances


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
    with sessions() as db:
        player = db.get(User, 10)
        battle = battle_service.start_pve(db, player, "training")
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
