"""Versioned, authoritative combat events. Replay applies deltas without running rules."""

from copy import deepcopy

SCHEMA_VERSION = 1
EVENTS_PER_ACTION = 100
TYPES = {
    "move": "UNIT_MOVED", "attack": "UNIT_ATTACKED", "retaliation": "COUNTERATTACK",
    "defend": "UNIT_DEFENDED", "wait": "UNIT_WAITED", "skip": "UNIT_SKIPPED",
    "surrender": "SIDE_SURRENDERED", "battle_end": "BATTLE_FINISHED",
    "summon": "ELEMENTAL_SUMMONED",
}


def initial_events(state, partial):
    return [
        {"sequence": 0, "type": "REPLAY_CHECKPOINT" if partial else "BATTLE_STARTED",
         "payload": {}},
        {"sequence": 1, "type": "TURN_STARTED", "actor_id": state["active_id"], "payload": {}},
    ]


def action_events(before, after, legacy):
    result = []

    def emit(kind, payload, actor=None, target=None):
        event = {
            "sequence": after.seq * EVENTS_PER_ACTION + len(result), "action_sequence": after.seq,
            "type": kind, "payload": payload,
        }
        if actor is not None:
            event["actor_id"] = actor
        if target is not None:
            event["target_id"] = target
        result.append(event)

    finished = None
    for legacy_event in legacy:
        kind = legacy_event["type"]
        payload = {key: value for key, value in legacy_event.items() if key != "type"}
        actor = payload.get("stack", payload.get("attacker"))
        target = payload.get("target")
        if kind == "battle_end":
            finished = payload
            continue
        if kind == "move":
            stack = before.stacks[actor]
            payload.update({"from": [stack.x, stack.y], "to": payload["path"][-1], "path": payload["path"][1:]})
        emit(TYPES[kind], payload, actor, target)
        if kind in {"attack", "retaliation"}:
            emit("DAMAGE_APPLIED", {
                **payload, "creatures_before": payload["target_left"] + payload["killed"],
                "creatures_after": payload["target_left"],
            }, actor, target)
            if not payload["target_left"]:
                emit("UNIT_KILLED", {}, actor, target)

        if kind == "defend":
            emit("STATUS_APPLIED", {"effect": "defend", "expires": "next_own_turn"}, actor, actor)

    emit("TURN_ENDED", {}, None if after.surrendered is not None else before.active_id)
    if finished is not None:
        emit("BATTLE_FINISHED", finished)
    else:
        previous = before.stacks.get(after.active_id)
        if previous and previous.defending and not after.active().defending:
            emit("STATUS_EXPIRED", {"effect": "defend"}, after.active_id, after.active_id)
        emit("TURN_STARTED", {}, after.active_id)

    old, new = before.to_dict(), after.to_dict()
    result[-1]["changes"] = {
        "fields": {key: value for key, value in new.items() if key != "stacks" and old.get(key) != value},
        "stacks": {key: value for key, value in new["stacks"].items() if old["stacks"].get(key) != value},
        "removed_stacks": sorted(old["stacks"].keys() - new["stacks"].keys()),
    }
    return result


def reconstruct(initial_state, events):
    state = deepcopy(initial_state)
    for event in events:
        kind = event["type"]
        if kind == "UNIT_MOVED":
            stack = state["stacks"][event["actor_id"]]
            stack["x"], stack["y"] = event["payload"]["to"]
        elif kind == "DAMAGE_APPLIED":
            stack = state["stacks"][event["target_id"]]
            stack.update(count=event["payload"]["creatures_after"], top_hp=event["payload"]["top_hp"])
        elif kind in {"STATUS_APPLIED", "STATUS_EXPIRED"} and event["payload"]["effect"] == "defend":
            state["stacks"][event["target_id"]]["defending"] = kind == "STATUS_APPLIED"
        elif kind == "UNIT_KILLED":
            state["stacks"].pop(event["target_id"])
        changes = event.get("changes")
        if changes:
            state.update(changes["fields"])
            state["stacks"].update(deepcopy(changes["stacks"]))
            for key in changes["removed_stacks"]:
                state["stacks"].pop(key, None)
    return state
