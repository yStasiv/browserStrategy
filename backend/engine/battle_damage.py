"""Attribute recorded HP loss to creatures and heroes."""
from collections import Counter

from sqlalchemy import select

from .battle_models import Battle, BattleAction


def attributed_events(initial, events):
    units = {key: (stack["owner"], stack["unit"]) for key, stack in initial.get("stacks", {}).items()}
    heroes = initial.get("heroes", {})
    for event in events:
        if event["type"] == "DAMAGE_APPLIED":
            actor = event.get("actor_id")
            payload = event["payload"]
            before, after = payload.get("hp_before"), payload.get("hp_after")
            if isinstance(before, int) and isinstance(after, int) and before > after:
                if actor in heroes:
                    event = {**event, "hero_damage": {"side": heroes[actor]["owner"], "amount": before - after}}
                elif actor in units:
                    side, unit = units[actor]
                    event = {**event, "creature_damage": {"side": side, "unit": unit, "amount": before - after}}
        yield event
        for key, stack in event.get("changes", {}).get("stacks", {}).items():
            units[key] = (stack["owner"], stack["unit"])


def damage_summary(db, battle_id, seq):
    totals = {0: Counter(), 1: Counter()}
    battle = db.get(Battle, battle_id)
    initial = battle.initial_state or {}
    hero_totals = {hero["owner"]: 0 for hero in initial.get("heroes", {}).values()}
    partial = False
    if seq:
        partial = not initial or initial["seq"] != 0
        if initial:
            actions = db.scalars(select(BattleAction.replay_events).where(
                BattleAction.battle_id == battle_id, BattleAction.seq >= initial["seq"], BattleAction.seq < seq,
            ).order_by(BattleAction.seq))
            events = (event for action in actions if action for event in action)
            for event in attributed_events(initial, events):
                if damage := event.get("creature_damage"):
                    totals[damage["side"]][damage["unit"]] += damage["amount"]
                if damage := event.get("hero_damage"):
                    hero_totals[damage["side"]] += damage["amount"]
    return {"partial": partial, "sides": [
        {"side": side, "total": sum(creatures.values()), "hero_total": hero_totals.get(side), "creatures": [
            {"unit": unit, "amount": amount} for unit, amount in creatures.most_common()
        ]} for side, creatures in totals.items()
    ]}
