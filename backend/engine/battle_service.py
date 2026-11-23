"""Бізнес-логіка бою: рушій + БД. Рушій чистий, тут лише завантажити → зіграти → зберегти."""
from __future__ import annotations

import random
import secrets
from datetime import datetime
from typing import List

from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import models
from ..services.activity_guilds import HUNTERS, award_point
from ..services import castle_buildings
from ..services.rewards import issue_system_resources
from .battle_damage import attributed_events, damage_summary
from .battle_experience import earned_experience
from .battle_models import Battle, BattleAction, BattleParticipant
from .battle_result import completion_data
from ..engine import BattleState, IllegalAction, action_from_dict, create_battle, turn_info
from ..engine.data import PVE_SCENARIOS, SUMMONING, UNITS, UNIT_PRESENTATION, faction_key
from ..engine.flow import NotYourTurn, Step, advance_ai, play_turn, surrender_turn
from ..engine.rules import forecast
from .actions import action_to_dict
from .ai import choose_action
from .deployment import place, slot_limit
from .setup import ZONE_COLS
from .rules import init_timeline
from .events import SCHEMA_VERSION, initial_events
from .hero import make_hero
from .hunting import TARGETS, offers, squad_count
from .roster import saved_army
from .summoning import available_elements, hp_pool, max_energy


class BattleError(Exception):
    status_code = 400


class ArmyRequired(BattleError):
    pass


class NotFound(BattleError):
    status_code = 404


class Forbidden(BattleError):
    status_code = 403


class Conflict(BattleError):
    status_code = 409


def user_level(user) -> int:
    # TODO: підставте реальне поле бойового рівня з models.User
    return int(getattr(user, "combat_level", None) or getattr(user, "level", None) or 1)


# ---------- представлення для клієнта ----------

DEPLOYMENT = "deployment"
PVE_VICTORY_GOLD = (32, 298)


def _view(db, battle_id: int, mode: str, status: str, version: int, winner_side, state: BattleState,
          my_side: int, events: list, steps=(), level=None, completion=None) -> dict:
    active = state.active()
    return {
        "id": battle_id,
        "mode": mode,
        "status": status,
        "version": version,
        "winner_side": winner_side,
        **(completion or {"reward": None, "result": None}),
        "my_side": my_side,
        "state": state.to_dict(),
        "creature_damage": damage_summary(db, battle_id, state.seq),
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
    battle = db.get(Battle, battle_id)
    if battle.mode != "pve":
        return  # PvP-нагороди й рейтинг — окремий крок
    initial = BattleState.from_dict(battle.initial_state) if battle.initial_state else state
    parts = db.query(BattleParticipant).filter(BattleParticipant.battle_id == battle_id,
                                               BattleParticipant.user_id.isnot(None)).all()
    for p in parts:
        xp = earned_experience(initial, state, p.side)
        gold = random.randint(*PVE_VICTORY_GOLD) if state.winner == p.side else 0
        rewarded_hunt = state.hunt_key and state.winner == p.side
        entries = [{"type": "experience", "amount": xp}]
        if rewarded_hunt:
            entries.append({"type": "hunters", "amount": 1})
        issue_system_resources(db, p.user_id, "battle_v1", str(battle_id),
                               gold=gold, wood=0, stone=0, experience=xp, reward_entries=entries)
        if rewarded_hunt:
            award_point(db, p.user_id, HUNTERS)


def legacy_battle_experience(state, side):
    if state.surrendered == side or (state.hunt_key and state.winner != side):
        return 0
    return 50 if state.winner == side else 10


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
    return _view(db, battle.id, battle.mode, battle.status, battle.version, battle.winner_side,
                 state, side, [], level=battle.level,
                 completion=completion_data(db, battle_id, state, user.id, legacy_battle_experience))


def start_pve(db: Session, user, scenario_key: str, *, hunting=False, expected_difficulty=None) -> dict:
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

    level = user_level(user)
    hunt_level = None
    if hunting:
        hunt = TARGETS.get(scenario_key)
        if hunt is None:
            raise NotFound("Невідома ціль полювання.")
        if level < hunt.min_level:
            raise Forbidden("Бойовий рівень занизький для цієї цілі.")
        offered = {target.creature: difficulty for target, difficulty in offers(db, user.id, level)}
        hunt_level = offered.get(scenario_key)
        if hunt_level is None or (expected_difficulty is not None and hunt_level != expected_difficulty):
            raise Conflict("Цілі полювання змінилися. Онови карту.")
        scenario = {"min_level": hunt.min_level, "army": [(hunt.creature, squad_count(hunt, hunt_level))]}
    else:
        scenario = PVE_SCENARIOS.get(scenario_key)
    if scenario is None:
        raise NotFound("невідомий сценарій")
    if level < scenario["min_level"]:
        raise Forbidden("рівень занадто низький для цього сценарію")

    army = saved_army(db, user.id)
    if not army:
        raise ArmyRequired("Спочатку набери військо в Замку.")
    try:
        state = create_battle(army, scenario["army"],
                              seed=secrets.randbits(31), level=level, mode="pve")
    except ValueError as e:
        raise BattleError(str(e))
    if hunting:
        state.hunt_key = scenario_key
        state.hunt_level = hunt_level
    hero = make_hero(db, user, 0, level)
    state.heroes[hero.id] = hero
    school = 0
    if faction_key(user.fraction) == "elves":
        entries, _ = castle_buildings.catalog()
        school = castle_buildings.school_level(castle_buildings.built_ids(db, user, entries))
    energy = max_energy(hero.knowledge)
    state.summoning["0"] = {
        "school_level": school, "energy": energy, "max_energy": energy,
        "hp_pool": hp_pool(hero.spell_power), "cost": SUMMONING["energy_cost"],
        "elements": available_elements(school),
    }
    state.status = DEPLOYMENT
    state.active_id = None
    battle = Battle(mode="pve", level=level, status=DEPLOYMENT, state=state.to_dict(), version=0)
    db.add(battle)
    db.flush()
    db.add_all([BattleParticipant(battle_id=battle.id, side=0, user_id=user.id),
                BattleParticipant(battle_id=battle.id, side=1, user_id=None)])
    db.commit()
    return _view(db, battle.id, battle.mode, DEPLOYMENT, 0, None, state, 0, [], level=level)


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
    return _view(db, battle_id, battle.mode, state.status, version + 1,
                 state.winner, state, side, _flat_events(steps), steps, level=battle.level,
                 completion=completion_data(db, battle_id, state, user.id, legacy_battle_experience))


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
    return _view(db, battle_id, battle.mode, new_state.status if new_state.status == "finished" else "active",
                 expected_version + 1, new_state.winner, new_state, mine.side, _flat_events(steps), steps,
                 completion=completion_data(db, battle_id, new_state, user.id, legacy_battle_experience))


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
    return _view(db, battle_id, battle.mode, "finished", expected_version + 1, new_state.winner,
                 new_state, mine.side, _flat_events(steps), steps,
                 completion=completion_data(db, battle_id, new_state, user.id, legacy_battle_experience))


def submit_auto_action(db, user, battle_id, expected_version):
    battle, side = _owned_battle(db, user, battle_id)
    if battle.version != expected_version:
        raise Conflict("Стан бою змінився.")
    state = BattleState.from_dict(battle.state)
    actor = state.active()
    if actor is None or actor.owner != side:
        raise Conflict("Зараз немає доступного ходу.")
    return submit_action(db, user, battle_id, action_to_dict(choose_action(state)), expected_version)


def replay_history(db, user, limit=20, *, detailed=False):
    columns = [Battle.id, Battle.initial_state.is_not(None).label("available")]
    if detailed:
        columns += [Battle.created_at, Battle.initial_state, Battle.state, BattleParticipant.side]
    query = (db.query(*columns).join(BattleParticipant)
             .filter(BattleParticipant.user_id == user.id, Battle.status == "finished")
             .order_by(Battle.id.desc()))
    rows = query.limit(limit).all() if limit is not None else query.all()
    history = []
    for row in rows:
        entry = {"id": row.id, "available": row.available}
        if detailed:
            start = row.initial_state
            complete = start is not None and start.get("seq") == 0
            counts = {}
            for stack in (start or row.state).get("stacks", {}).values():
                if stack["owner"] != row.side and not stack.get("summoned"):
                    key = stack["unit"]
                    counts[key] = counts.get(key, 0) + stack["count"]
            entry.update(
                created_at=row.created_at,
                hunt=bool(row.state.get("hunt_key") or (start or {}).get("hunt_key")),
                enemies=[
                    {"name": UNITS[key].name if key in UNITS else "Невідома істота",
                     "count": count if complete else None}
                    for key, count in counts.items()
                ],
            )
        history.append(entry)
    return history


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
    completion = completion_data(db, battle_id, BattleState.from_dict(battle.state), user.id, legacy_battle_experience)
    if completion["result"] is None:
        completion["result"] = {"status": battle.status, "winner_side": battle.winner_side}
    return {
        "battle_id": battle_id, "schema_version": battle.replay_schema_version, "partial": partial,
        "initial_state": initial, "events": list(attributed_events(initial, events)), "final_state": battle.state,
        **completion, "my_side": side, "units": UNIT_PRESENTATION,
    }


def start_hunt(db, user, creature_key, expected_difficulty=None):
    return start_pve(db, user, creature_key, hunting=True, expected_difficulty=expected_difficulty)


def hunting_options(db, player, traveling):
    level = user_level(player)
    result = []
    for target, difficulty in offers(db, player.id, level):
        creature = UNITS[target.creature]
        result.append({
            "key": creature.key, "name": creature.name, "icon": creature.icon,
            "image_url": creature.image_url,
            "count": squad_count(target, difficulty), "min_level": target.min_level, "difficulty": difficulty,
            "gold_min": PVE_VICTORY_GOLD[0], "gold_max": PVE_VICTORY_GOLD[1],
            "available": not traveling and level >= target.min_level,
        })
    return result
