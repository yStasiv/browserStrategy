"""Бізнес-логіка бою: рушій + БД. Рушій чистий, тут лише завантажити → зіграти → зберегти."""
from __future__ import annotations

import random
import secrets
from datetime import datetime
from typing import List

from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import models
from ..services.rewards import issue_system_resources
from .battle_models import ArmySlot, Battle, BattleAction, BattleParticipant
from ..engine import BattleState, IllegalAction, action_from_dict, create_battle, turn_info
from ..engine.data import DEFAULT_ARMY, PVE_SCENARIOS, UNITS, UNIT_PRESENTATION
from ..engine.flow import NotYourTurn, Step, advance_ai, play_turn, surrender_turn
from ..engine.rules import forecast
from .actions import action_to_dict
from .ai import choose_action
from .deployment import place, slot_limit
from .setup import ZONE_COLS
from .rules import init_timeline
from .events import SCHEMA_VERSION, initial_events


class BattleError(Exception):
    status_code = 400


class NotFound(BattleError):
    status_code = 404


class Forbidden(BattleError):
    status_code = 403


class Conflict(BattleError):
    status_code = 409


def user_level(user) -> int:
    # TODO: підставте реальне поле бойового рівня з models.User
    return int(getattr(user, "combat_level", None) or getattr(user, "level", None) or 1)


# ---------- армія ----------

def get_army(db: Session, user_id: int) -> List[tuple]:
    slots = db.query(ArmySlot).filter(ArmySlot.user_id == user_id).order_by(ArmySlot.slot).all()
    if not slots:  # новий персонаж отримує армію за замовчуванням
        for i, (key, count) in enumerate(DEFAULT_ARMY):
            db.add(ArmySlot(user_id=user_id, slot=i, unit_key=key, count=count))
        db.flush()
        return list(DEFAULT_ARMY)
    return [(s.unit_key, s.count) for s in slots]


# ---------- представлення для клієнта ----------

DEPLOYMENT = "deployment"
PVE_VICTORY_GOLD = (32, 298)
PVE_VICTORY_XP = 50


def _view(battle_id: int, mode: str, status: str, version: int, winner_side, state: BattleState,
          my_side: int, events: list, steps=(), level=None, reward=None) -> dict:
    active = state.active()
    return {
        "id": battle_id,
        "mode": mode,
        "status": status,
        "version": version,
        "winner_side": winner_side,
        "reward": reward,
        "my_side": my_side,
        "state": state.to_dict(),
        "units": UNIT_PRESENTATION,
        "turn": turn_info(state) if active and active.owner == my_side else None,
        "forecast": forecast(state, 50),   # орієнтовна черга на 50 ходів уперед
        "events": events,
        "deployment": {
            "zone_width": ZONE_COLS, "max_slots": slot_limit(level, mode),
        } if status == DEPLOYMENT else None,
        "event_stream": [e for step in steps for e in step.replay_events],
    }


def _log_steps(db: Session, battle_id: int, first_seq: int, steps: List[Step]) -> None:
    for i, st in enumerate(steps):
        db.add(BattleAction(battle_id=battle_id, seq=first_seq + i, side=st.side,
                            action=st.action, events=st.events, replay_events=st.replay_events))


def _flat_events(steps: List[Step]) -> list:
    return [dict(e, side=st.side) for st in steps for e in st.events]


# ---------- нагороди ----------

def _settle(db: Session, battle_id: int, state: BattleState) -> None:
    """Видає нагороди рівно один раз: прапорець rewarded ставиться атомарно."""
    res = db.execute(update(Battle)
                     .where(Battle.id == battle_id, Battle.rewarded.is_(False))
                     .values(rewarded=True))
    if res.rowcount != 1:
        return
    mode = db.get(Battle, battle_id).mode
    if mode != "pve":
        return  # PvP-нагороди й рейтинг — окремий крок
    parts = db.query(BattleParticipant).filter(BattleParticipant.battle_id == battle_id,
                                               BattleParticipant.user_id.isnot(None)).all()
    for p in parts:
        xp = battle_experience(state, p.side)
        gold = random.randint(*PVE_VICTORY_GOLD) if state.winner == p.side else 0
        issue_system_resources(db, p.user_id, "battle_v1", str(battle_id),
                               gold=gold, wood=0, stone=0, experience=xp)


def battle_experience(state, side):
    if state.surrendered == side or (state.hunt_key and state.winner != side):
        return 0
    return PVE_VICTORY_XP if state.winner == side else 10


def recorded_reward(db, battle_id, user_id, state, side):
    if state.status != "finished":
        return None
    entry = db.query(models.RewardTransaction).filter_by(
        source="battle_v1", source_key=str(battle_id), recipient_id=user_id,
    ).one_or_none()
    if entry is None:
        return None
    return {"gold": entry.gold, "experience": battle_experience(state, side)}


def _finish_fields(state: BattleState) -> dict:
    if state.status != "finished":
        return {}
    return {"status": "finished", "winner_side": state.winner, "finished_at": datetime.utcnow()}


# ---------- публічне API сервісу ----------

def get_active_battle_id(db: Session, user_id: int):
    row = (db.query(Battle.id)
           .join(BattleParticipant, BattleParticipant.battle_id == Battle.id)
           .filter(BattleParticipant.user_id == user_id, Battle.status.in_(("active", DEPLOYMENT)))
           .order_by(Battle.id.desc()).first())
    return row[0] if row else None


def _owned_battle(db: Session, user, battle_id: int):
    battle = db.get(Battle, battle_id)
    if battle is None:
        raise NotFound("бій не знайдено")
    part = (db.query(BattleParticipant)
            .filter_by(battle_id=battle_id, user_id=user.id).first())
    if part is None:
        raise Forbidden("ви не учасник цього бою")
    return battle, part.side


def get_battle_view(db: Session, user, battle_id: int) -> dict:
    battle, side = _owned_battle(db, user, battle_id)
    state = BattleState.from_dict(battle.state)
    return _view(battle.id, battle.mode, battle.status, battle.version, battle.winner_side,
                 state, side, [], level=battle.level, reward=recorded_reward(db, battle_id, user.id, state, side))


def start_pve(db: Session, user, scenario_key: str, *, hunting=False) -> dict:
    if hunting:
        from backend.services.world import resolve_location
        journey, _ = resolve_location(db, user)
        if journey is not None:
            raise Conflict("Полювання недоступне під час подорожі.")
    else:
        db.execute(update(models.User).where(models.User.id == user.id).values(map_sector=models.User.map_sector))
    existing = get_active_battle_id(db, user.id)
    if existing:  # один активний бій на гравця: відновлюємо його
        result = get_battle_view(db, user, existing)
        db.commit()
        return result

    if hunting:
        creature = UNITS.get(scenario_key)
        hunt = creature.hunting if creature else None
        scenario = {"min_level": hunt.min_level, "army": [(creature.key, hunt.count)]} if hunt else None
    else:
        scenario = PVE_SCENARIOS.get(scenario_key)
    if scenario is None:
        raise NotFound("невідомий сценарій")
    level = user_level(user)
    if level < scenario["min_level"]:
        raise Forbidden("рівень занадто низький для цього сценарію")

    try:
        state = create_battle(get_army(db, user.id), scenario["army"],
                              seed=secrets.randbits(31), level=level, mode="pve")
    except ValueError as e:
        raise BattleError(str(e))
    if hunting:
        state.hunt_key = scenario_key
    state.status = DEPLOYMENT
    state.active_id = None
    battle = Battle(mode="pve", level=level, status=DEPLOYMENT, state=state.to_dict(), version=0)
    db.add(battle)
    db.flush()
    db.add_all([BattleParticipant(battle_id=battle.id, side=0, user_id=user.id),
                BattleParticipant(battle_id=battle.id, side=1, user_id=None)])
    db.commit()
    return _view(battle.id, battle.mode, DEPLOYMENT, 0, None, state, 0, [], level=level)


def update_deployment(db, user, battle_id, version, placement=None):
    battle, side = _owned_battle(db, user, battle_id)
    if battle.status != DEPLOYMENT or battle.version != version:
        raise Conflict("Стан розстановки змінився.")
    state = BattleState.from_dict(battle.state)
    extra = {}
    steps = []
    if placement is not None:
        try:
            place(state, side, *placement, limit=slot_limit(battle.level, battle.mode))
        except ValueError as exc:
            raise BattleError(str(exc)) from exc
    else:
        state.status = "active"
        init_timeline(state)
        extra = {"initial_state": state.to_dict(), "replay_schema_version": SCHEMA_VERSION}
        ai_sides = {row.side for row in db.query(BattleParticipant).filter_by(battle_id=battle_id, user_id=None)}
        state, steps = advance_ai(state, ai_sides)
        extra.update(_finish_fields(state))
        extra["winner_side"] = state.winner
    result = db.execute(
        update(Battle).where(Battle.id == battle_id, Battle.version == version, Battle.status == DEPLOYMENT)
        .values(state=state.to_dict(), version=version + 1, status=state.status,
                **{key: value for key, value in extra.items() if key != "status"})
    )
    if result.rowcount != 1:
        db.rollback()
        raise Conflict("Стан розстановки змінився.")
    _log_steps(db, battle_id, 0, steps)
    if state.status == "finished":
        _settle(db, battle_id, state)
    db.commit()
    return _view(battle_id, battle.mode, state.status, version + 1,
                 state.winner, state, side, _flat_events(steps), steps, level=battle.level,
                 reward=recorded_reward(db, battle_id, user.id, state, side))


def _checkpoint(battle):
    if battle.initial_state is None:
        return {"initial_state": battle.state, "replay_schema_version": SCHEMA_VERSION}
    return {}


def submit_action(db: Session, user, battle_id: int, action_dict: dict, expected_version: int) -> dict:
    battle = db.get(Battle, battle_id)
    if battle is None:
        raise NotFound("бій не знайдено")
    parts = db.query(BattleParticipant).filter_by(battle_id=battle_id).all()
    mine = next((p for p in parts if p.user_id == user.id), None)
    if mine is None:
        raise Forbidden("ви не учасник цього бою")
    if battle.status != "active":
        raise BattleError("бій завершено")
    if battle.version != expected_version:
        raise Conflict("стан бою змінився, оновіть сторінку")

    old_state = BattleState.from_dict(battle.state)
    ai_sides = {p.side for p in parts if p.user_id is None}
    try:
        action = action_from_dict(action_dict)
        new_state, steps = play_turn(old_state, mine.side, action, ai_sides)
    except NotYourTurn as e:
        raise Conflict(str(e))
    except (IllegalAction, ValueError, KeyError, TypeError) as e:
        raise BattleError(f"недопустима дія: {e}")

    # Оптимістичне блокування: запис пройде, лише якщо версію ніхто не змінив
    res = db.execute(update(Battle)
                     .where(Battle.id == battle_id, Battle.version == expected_version)
                     .values(state=new_state.to_dict(), version=expected_version + 1,
                             **_finish_fields(new_state), **_checkpoint(battle)))
    if res.rowcount != 1:
        db.rollback()
        raise Conflict("стан бою змінився, спробуйте ще раз")
    _log_steps(db, battle_id, old_state.seq, steps)
    if new_state.status == "finished":
        _settle(db, battle_id, new_state)
    db.commit()
    return _view(battle_id, battle.mode, new_state.status if new_state.status == "finished" else "active",
                 expected_version + 1, new_state.winner, new_state, mine.side, _flat_events(steps), steps,
                 reward=recorded_reward(db, battle_id, user.id, new_state, mine.side))


def surrender_battle(db: Session, user, battle_id: int, expected_version: int) -> dict:
    """Здача: можна в будь-який момент активного бою (не лише у свій хід)."""
    battle = db.get(Battle, battle_id)
    if battle is None:
        raise NotFound("бій не знайдено")
    parts = db.query(BattleParticipant).filter_by(battle_id=battle_id).all()
    mine = next((p for p in parts if p.user_id == user.id), None)
    if mine is None:
        raise Forbidden("ви не учасник цього бою")
    if battle.status != "active":
        raise BattleError("бій завершено")
    if battle.version != expected_version:
        raise Conflict("стан бою змінився, оновіть сторінку")

    old_state = BattleState.from_dict(battle.state)
    try:
        new_state, steps = surrender_turn(old_state, mine.side)
    except IllegalAction as e:
        raise BattleError(str(e))

    res = db.execute(update(Battle)
                     .where(Battle.id == battle_id, Battle.version == expected_version)
                     .values(state=new_state.to_dict(), version=expected_version + 1,
                             **_finish_fields(new_state), **_checkpoint(battle)))
    if res.rowcount != 1:
        db.rollback()
        raise Conflict("стан бою змінився, спробуйте ще раз")
    _log_steps(db, battle_id, old_state.seq, steps)
    _settle(db, battle_id, new_state)
    db.commit()
    return _view(battle_id, battle.mode, "finished", expected_version + 1, new_state.winner,
                 new_state, mine.side, _flat_events(steps), steps,
                 reward=recorded_reward(db, battle_id, user.id, new_state, mine.side))


def submit_auto_action(db, user, battle_id, expected_version):
    battle, side = _owned_battle(db, user, battle_id)
    if battle.version != expected_version:
        raise Conflict("Стан бою змінився.")
    state = BattleState.from_dict(battle.state)
    actor = state.active()
    if actor is None or actor.owner != side:
        raise Conflict("Зараз немає доступного ходу.")
    return submit_action(db, user, battle_id, action_to_dict(choose_action(state)), expected_version)


def replay_history(db, user, limit=20):
    query = (db.query(Battle.id, Battle.initial_state.is_not(None).label("available")).join(BattleParticipant)
             .filter(BattleParticipant.user_id == user.id, Battle.status == "finished")
             .order_by(Battle.id.desc()))
    rows = query.limit(limit).all() if limit is not None else query.all()
    return [{"id": row.id, "available": row.available} for row in rows]


def battle_events(db, user, battle_id, *, finished_only=False):
    battle, side = _owned_battle(db, user, battle_id)
    if finished_only and battle.status != "finished":
        raise Conflict("Повтор доступний після завершення бою.")
    initial = battle.initial_state
    if initial is None:
        raise NotFound("Для цього бою немає початкового знімка повтору.")
    partial = initial["seq"] != 0
    events = initial_events(initial, partial)
    actions = (db.query(BattleAction).filter(
        BattleAction.battle_id == battle_id, BattleAction.seq >= initial["seq"],
        BattleAction.seq < battle.state["seq"],
    ).order_by(BattleAction.seq).all())
    for action in actions:
        events.extend(action.replay_events)
    return {
        "battle_id": battle_id, "schema_version": battle.replay_schema_version, "partial": partial,
        "initial_state": initial, "events": events, "final_state": battle.state,
        "reward": recorded_reward(db, battle_id, user.id, BattleState.from_dict(battle.state), side),
        "my_side": side, "units": UNIT_PRESENTATION, "result": {"status": battle.status, "winner_side": battle.winner_side},
    }


def start_hunt(db, user, creature_key):
    return start_pve(db, user, creature_key, hunting=True)


def hunting_options(player, traveling):
    level = user_level(player)
    return [
        {
            "key": creature.key, "name": creature.name, "icon": creature.icon,
            "count": creature.hunting.count, "min_level": creature.hunting.min_level,
            "difficulty": creature.hunting.difficulty,
            "gold_min": PVE_VICTORY_GOLD[0], "gold_max": PVE_VICTORY_GOLD[1], "xp": PVE_VICTORY_XP,
            "available": not traveling and level >= creature.hunting.min_level,
        }
        for creature in UNITS.values() if creature.hunting
    ]
