"""Бізнес-логіка бою: рушій + БД. Рушій чистий, тут лише завантажити → зіграти → зберегти."""
from __future__ import annotations

import random
import secrets
from datetime import datetime
from typing import List

from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import models
from .battle_models import ArmySlot, Battle, BattleAction, BattleParticipant
from ..engine import BattleState, IllegalAction, action_from_dict, create_battle, turn_info
from ..engine.data import DEFAULT_ARMY, PVE_SCENARIOS
from ..engine.flow import NotYourTurn, Step, advance_ai, play_turn, surrender_turn
from ..engine.rules import forecast


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

def _view(battle_id: int, mode: str, status: str, version: int, winner_side, state: BattleState,
          my_side: int, events: list) -> dict:
    active = state.active()
    return {
        "id": battle_id,
        "mode": mode,
        "status": status,
        "version": version,
        "winner_side": winner_side,
        "my_side": my_side,
        "state": state.to_dict(),
        "turn": turn_info(state) if active and active.owner == my_side else None,
        "forecast": forecast(state, 50),   # орієнтовна черга на 50 ходів уперед
        "events": events,
    }


def _log_steps(db: Session, battle_id: int, first_seq: int, steps: List[Step]) -> None:
    for i, st in enumerate(steps):
        db.add(BattleAction(battle_id=battle_id, seq=first_seq + i, side=st.side,
                            action=st.action, events=st.events))


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
        user = db.get(models.User, p.user_id)
        if user is None:
            continue
        if state.surrendered == p.side:
            continue                                # хто здався — без нагороди
        if state.winner == p.side:
            user.gold += random.randint(32, 298)   # TODO: нагорода зі сценарію
            user.experience += 50
        else:
            user.experience += 10


def _finish_fields(state: BattleState) -> dict:
    if state.status != "finished":
        return {}
    return {"status": "finished", "winner_side": state.winner, "finished_at": datetime.utcnow()}


# ---------- публічне API сервісу ----------

def get_active_battle_id(db: Session, user_id: int):
    row = (db.query(Battle.id)
           .join(BattleParticipant, BattleParticipant.battle_id == Battle.id)
           .filter(BattleParticipant.user_id == user_id, Battle.status == "active")
           .order_by(Battle.id.desc()).first())
    return row[0] if row else None


def get_battle_view(db: Session, user, battle_id: int) -> dict:
    battle = db.get(Battle, battle_id)
    if battle is None:
        raise NotFound("бій не знайдено")
    part = (db.query(BattleParticipant)
            .filter_by(battle_id=battle_id, user_id=user.id).first())
    if part is None:
        raise Forbidden("ви не учасник цього бою")
    return _view(battle.id, battle.mode, battle.status, battle.version, battle.winner_side,
                 BattleState.from_dict(battle.state), part.side, [])


def start_pve(db: Session, user, scenario_key: str) -> dict:
    existing = get_active_battle_id(db, user.id)
    if existing:  # один активний бій на гравця: відновлюємо його
        return get_battle_view(db, user, existing)

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
    state, steps = advance_ai(state, {1})  # якщо першим ходить ШІ

    battle = Battle(mode="pve", level=level, state=state.to_dict(), version=0, **_finish_fields(state))
    db.add(battle)
    db.flush()
    db.add_all([BattleParticipant(battle_id=battle.id, side=0, user_id=user.id),
                BattleParticipant(battle_id=battle.id, side=1, user_id=None)])
    _log_steps(db, battle.id, 0, steps)
    if state.status == "finished":
        _settle(db, battle.id, state)
    db.commit()
    return _view(battle.id, "pve", "finished" if state.status == "finished" else "active", 0,
                 state.winner, state, 0, _flat_events(steps))


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
                             **_finish_fields(new_state)))
    if res.rowcount != 1:
        db.rollback()
        raise Conflict("стан бою змінився, спробуйте ще раз")
    _log_steps(db, battle_id, old_state.seq, steps)
    if new_state.status == "finished":
        _settle(db, battle_id, new_state)
    db.commit()
    return _view(battle_id, battle.mode, new_state.status if new_state.status == "finished" else "active",
                 expected_version + 1, new_state.winner, new_state, mine.side, _flat_events(steps))


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
                             **_finish_fields(new_state)))
    if res.rowcount != 1:
        db.rollback()
        raise Conflict("стан бою змінився, спробуйте ще раз")
    _log_steps(db, battle_id, old_state.seq, steps)
    _settle(db, battle_id, new_state)
    db.commit()
    return _view(battle_id, battle.mode, "finished", expected_version + 1, new_state.winner,
                 new_state, mine.side, _flat_events(steps))
