"""Attribute recorded HP loss to creature types without changing combat events on disk."""
from collections import Counter

from sqlalchemy import select

from .battle_models import Battle, BattleAction


def attributed_events(initial, events):
    units = {key: (stack["owner"], stack["unit"]) for key, stack in initial.get("stacks", {}).items()}
    for event in events:
        if event["type"] == "DAMAGE_APPLIED" and (source := units.get(event.get("actor_id"))) is not None:
            payload = event["payload"]
            before, after = payload.get("hp_before"), payload.get("hp_after")
            if isinstance(before, int) and isinstance(after, int) and before > after:
                event = {**event, "creature_damage": {"side": source[0], "unit": source[1], "amount": before - after}}
        yield event
        for key, stack in event.get("changes", {}).get("stacks", {}).items():
            units[key] = (stack["owner"], stack["unit"])


def damage_summary(db, battle_id, seq):
    totals = {0: Counter(), 1: Counter()}
    partial = False
    if seq:
        battle = db.get(Battle, battle_id)
        initial = battle.initial_state
        partial = not initial or initial["seq"] != 0
        if initial:
            actions = db.scalars(select(BattleAction.replay_events).where(
                BattleAction.battle_id == battle_id, BattleAction.seq >= initial["seq"], BattleAction.seq < seq,
            ).order_by(BattleAction.seq))
            events = (event for action in actions if action for event in action)
            for event in attributed_events(initial, events):
                if damage := event.get("creature_damage"):
                    totals[damage["side"]][damage["unit"]] += damage["amount"]
    return {"partial": partial, "sides": [
        {"side": side, "total": sum(creatures.values()), "creatures": [
            {"unit": unit, "amount": amount} for unit, amount in creatures.most_common()
        ]} for side, creatures in totals.items()
    ]}
