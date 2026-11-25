"""Read-only aggregation for the administration dashboard. Database timestamps are UTC."""
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, func, select

from backend.engine.battle_models import Battle, BattleAction, BattleParticipant
from backend.engine.data import CONTENT, ELEMENTALS, UNITS
from backend.engine.events import SCHEMA_VERSION
from backend.engine.state import MAX_ACTIONS, BattleState
from backend.engine.battle_service import legacy_battle_experience
from backend.guild_models import ActivityGuildProgress
from backend.models import GameplayEvent, RewardTransaction, User
from backend.services.activity_guilds import METALWORKERS
from backend.services.artifact_shop import BONUS_LABELS, SHOP_CATEGORIES
from backend.services.resource_balances import resource_definitions

PERIODS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "all": None}
OUTCOMES = ("win", "loss", "draw", "surrender")
CATEGORIES = {key: label for label, _, keys in SHOP_CATEGORIES.values() for key in keys if key != "armor:"}
ITEM_ROOT = CONTENT.parent / "frontend/static/images/items"


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def catalog_integrity(catalog=CONTENT / "artifacts.json", root=ITEM_ROOT):
    try:
        rows = json.loads(catalog.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("Очікується список артефактів.")
    except (OSError, ValueError) as exc:
        return {"checked": 0, "ok": False, "issues": [{"name": "artifacts.json", "errors": [str(exc)]}]}, []

    resources = resource_definitions()
    issues, items = [], []
    seen = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            issues.append({"name": f"Запис {index}", "errors": ["Очікується об’єкт."]})
            continue
        name, kind, url = (row.get(key) for key in ("name", "item_type", "image_url"))
        errors = []
        if not isinstance(name, str) or not name.strip():
            errors.append("Відсутня назва.")
            name = f"Запис {index}"
        if not isinstance(row.get("description"), str) or not row["description"].strip():
            errors.append("Відсутній опис.")
        known_kind = isinstance(kind, str) and kind in CATEGORIES
        if not known_kind:
            errors.append("Невідомий тип предмета.")
        if known_kind:
            if (name, kind) in seen:
                errors.append("Дублікат предмета.")
            seen.add((name, kind))
        prefix = f"/static/images/items/{kind}/"
        category_root = root / str(kind)
        asset = category_root / url[len(prefix):] if isinstance(url, str) and "\x00" not in url and url.startswith(prefix) else None
        if (not known_kind or asset is None or ".." in asset.parts or not asset.is_file()
                or not category_root.resolve().is_relative_to(root.resolve())
                or not asset.resolve().is_relative_to(category_root.resolve())):
            errors.append("Зображення відсутнє або шлях виходить за межі категорії.")
        durability, maximum = row.get("durability"), row.get("max_durability")
        if not _integer(durability) or not _integer(maximum, 1) or durability > maximum:
            errors.append("Некоректна міцність.")
        stats = row.get("stats")
        if not isinstance(stats, dict) or any(key not in BONUS_LABELS or type(value) not in (int, float)
                                              for key, value in stats.items()):
            errors.append("Некоректні характеристики.")
        shop = row.get("shop_data")
        if isinstance(shop, dict):
            level, quantity, cost = shop.get("level"), shop.get("quantity", -1), shop.get("resources", {})
            if (not _integer(level, 1) or not _integer(shop.get("price"))
                    or not _integer(quantity, -1) or not isinstance(cost, dict)
                    or any(key == "gold" or key not in resources or not _integer(value) for key, value in cost.items())):
                errors.append("Некоректні ціна, рівень, ресурси або запас магазину.")
            if known_kind and _integer(level, 1):
                items.append((name, kind, level))
        else:
            errors.append("Відсутні дані магазину.")
        repair = row.get("repair_cost")
        if not isinstance(repair, dict) or not _integer(repair.get("gold"), 1):
            errors.append("Некоректна ціна ремонту.")
        if errors:
            issues.append({"name": name, "image_url": url if isinstance(url, str) else None, "errors": errors})
    return {"checked": len(rows), "ok": not issues, "issues": issues}, items


def _range(column, start, now):
    return (column <= now,) if start is None else (column >= start, column <= now)


def _percent(count, total):
    return round(100 * count / total, 2) if total else 0


def _average(total, count):
    return round(total / count, 2) if count else 0


def _labels(rows):
    return [{"label": str(label), "value": value} for label, value in rows]


def _timestamp(moment):
    return moment.replace(tzinfo=UTC).isoformat()


def _unit_name(key):
    return UNITS[key].name if key in UNITS else key


def _reward_resources(entry, resources):
    amounts = Counter(gold=entry.gold, singing_resin=entry.wood, basalt_bone=entry.stone)
    for detail in entry.reward_entries or ():
        resource, amount = detail.get("type"), detail.get("amount", detail.get("value"))
        if resource in resources and resource not in {"gold", "singing_resin", "basalt_bone"} and _integer(amount):
            amounts[resource] += amount
    return amounts


def _economy(db, start, now, bucket, resources, catalog_items):
    flows = defaultdict(lambda: defaultdict(Counter))
    purchases = Counter()
    repairs = Counter()
    for entry in db.scalars(select(RewardTransaction).where(
        *_range(RewardTransaction.created_at, start, now),
    ).execution_options(yield_per=500)):
        flows[bucket(entry.created_at)]["earned"].update(_reward_resources(entry, resources))

    for event in db.scalars(select(GameplayEvent).where(
        *_range(GameplayEvent.occurred_at, start, now),
    ).execution_options(yield_per=500)):
        payload = event.payload
        flow = flows[bucket(event.occurred_at)]
        if event.kind == "shop_purchase":
            purchases[payload["name"], payload["item_type"], payload["level"]] += 1
            flow["shop"].update(payload["costs"])
        elif event.kind == "repair_started":
            repairs["attempts"] += 1
            repairs["failures"] += int(not payload["succeeded"])
            flow["repairs"]["gold"] += payload["gold"]
        elif event.kind == "repair_refund":
            flow["refunded"]["gold"] += payload["gold"]
        elif event.kind == "item_broken":
            repairs["items_broken"] += 1

    totals = defaultdict(Counter)
    for flow in flows.values():
        for kind, amounts in flow.items():
            totals[kind].update(amounts)
    categories = Counter(dict.fromkeys(CATEGORIES, 0))
    levels = Counter(dict.fromkeys(range(1, 11), 0))
    for (_, kind, level), count in purchases.items():
        categories[kind] += count
        levels[level] += count
    ranked = sorted(set(catalog_items) | purchases.keys(), key=lambda item: (-purchases[item], item))

    def item_row(item):
        return dict(zip(("name", "item_type", "level", "count"), (*item, purchases[item])))

    avg, maximum = db.execute(select(func.avg(ActivityGuildProgress.points), func.max(ActivityGuildProgress.points))
                              .where(ActivityGuildProgress.guild == METALWORKERS)).one()
    shop = {
        "total": purchases.total(), "top": [item_row(item) for item in ranked if purchases[item]][:10],
        "bottom": [item_row(item) for item in sorted(ranked, key=lambda i: (purchases[i], i))[:10]],
        "categories": dict(categories), "levels": dict(sorted(levels.items())),
    }
    economy = {"resources": _flow_row(totals, resources), "repairs": {
        "attempts": repairs["attempts"], "failures": repairs["failures"],
        "failure_rate": _percent(repairs["failures"], repairs["attempts"]),
        "items_broken": repairs["items_broken"], "avg_guild_points": float(avg or 0), "max_guild_points": float(maximum or 0),
    }}
    return shop, economy, flows


def _flow_row(flow, resources):
    row = {kind: {key: flow.get(kind, {}).get(key, 0) for key in resources}
           for kind in ("earned", "shop", "repairs", "refunded")}
    row["spent"] = {key: row["shop"][key] + row["repairs"][key] for key in resources}
    return row


def _combat(db, start, now, bucket, limit):
    finished = func.coalesce(Battle.finished_at, Battle.created_at)
    scope = (Battle.status == "finished", *_range(finished, start, now))
    participants = defaultdict(list)
    for battle_id, side, username in db.execute(
        select(BattleParticipant.battle_id, BattleParticipant.side, User.username)
        .join(Battle, Battle.id == BattleParticipant.battle_id).join(User, User.id == BattleParticipant.user_id)
        .where(*scope).order_by(BattleParticipant.side, BattleParticipant.id)
    ):
        participants[battle_id].append((side, username))

    hunts = defaultdict(Counter)
    difficulty = defaultdict(Counter)
    volumes = defaultdict(Counter)
    outcomes = Counter()
    recent = []
    summoning = {}
    actions = action_cap = 0
    for battle_id, moment, mode, winner, state, has_replay, magic in db.execute(
        select(Battle.id, finished, Battle.mode, Battle.winner_side, Battle.state,
               (Battle.replay_schema_version == SCHEMA_VERSION) & Battle.initial_state.is_not(None),
               Battle.initial_state["summoning"])
        .where(*scope).order_by(finished.desc(), Battle.id.desc()).execution_options(yield_per=500)
    ):
        if magic:
            summoning[battle_id] = magic
        members = participants.get(battle_id) or [(0, None)]
        outcome = ("surrender" if state.get("surrendered") is not None else "draw" if winner is None
                   else "win" if winner == members[0][0] else "loss")
        count = state.get("seq", 0)
        hit_cap = outcome == "draw" and count >= MAX_ACTIONS
        actions += count
        action_cap += hit_cap
        outcomes[outcome] += 1
        volumes[bucket(moment)][outcome] += 1
        target = state.get("hunt_key")
        if target:
            hunts[target]["battles"] += 1
            difficulty[target][state.get("hunt_level") or 1] += 1
        if len(recent) < limit:
            if not target and mode == "pve":
                target_names = dict.fromkeys(_unit_name(stack["unit"]) for stack in state.get("stacks", {}).values()
                                             if stack.get("owner") != members[0][0] and stack.get("unit"))
                target = ", ".join(target_names)
            recent.append({
                "id": battle_id, "at": _timestamp(moment), "outcome": outcome, "actions": count, "hit_cap": hit_cap,
                "participants": [name for _, name in members if name], "target": _unit_name(target) if target else None,
                "replay_url": f"/battle?replay={battle_id}&admin_replay=1" if has_replay else None,
            })

    for state, recipient_side, reward in db.execute(
        select(Battle.state, BattleParticipant.side, RewardTransaction)
        .select_from(Battle).join(RewardTransaction, (RewardTransaction.source == "battle_v1")
              & (RewardTransaction.source_key == cast(Battle.id, String)))
        .join(BattleParticipant, (BattleParticipant.battle_id == Battle.id)
              & (BattleParticipant.user_id == RewardTransaction.recipient_id), isouter=True)
        .where(*scope).execution_options(yield_per=500)
    ):
        if target := state.get("hunt_key"):
            hunts[target]["gold"] += reward.gold
            if reward.reward_entries is None and recipient_side is not None:
                hunts[target]["xp"] += legacy_battle_experience(
                    BattleState.from_dict(state), recipient_side,
                )
            else:
                hunts[target]["xp"] += sum(row.get("amount", row.get("value", 0))
                                           for row in reward.reward_entries or () if row.get("type") == "experience")

    rolls = defaultdict(Counter)
    summons = Counter()
    spell_tiers = {key: row["school_level"] for key, row in ELEMENTALS.items()}
    for events, side, battle_id in db.execute(
        select(BattleAction.replay_events, BattleAction.side, BattleAction.battle_id)
        .join(Battle, Battle.id == BattleAction.battle_id)
        .where(*scope, BattleAction.replay_events.is_not(None)).execution_options(yield_per=500)
    ):
        for event in events or ():
            kind, payload = event.get("type"), event.get("payload", {})
            if kind in {"LUCK_ROLLED", "MORALE_ROLLED"} and payload.get("stat"):
                sign = "positive" if payload["stat"] > 0 else "negative"
                stats = rolls[kind.partition("_")[0].lower(), sign]
                stats["checks"] += 1
                if payload.get("outcome") == sign:
                    stats["procs"] += 1
                    stats["streak"] += payload.get("streak_before", 1)
            elif kind == "ELEMENTAL_SUMMONED":
                magic = summoning.get(battle_id, {}).get(str(side), {})
                tier = magic.get("school_level") or spell_tiers.get(payload.get("spell"))
                summons[str(tier) if tier else "Невідомий"] += 1

    total = outcomes.total()
    combat = {"total": total, "avg_actions": _average(actions, total), "draw_cap": action_cap,
              "outcomes": {key: {"count": outcomes[key], "percent": _percent(outcomes[key], total)}
                           for key in OUTCOMES}}
    hunting = [{"key": key, "target": _unit_name(key), "battles": stats["battles"],
                "avg_gold": _average(stats["gold"], stats["battles"]), "avg_xp": _average(stats["xp"], stats["battles"]),
                "difficulty": dict(sorted(difficulty[key].items()))}
               for key, stats in sorted(hunts.items(), key=lambda row: (-row[1]["battles"], row[0]))]
    effects = {
        "rolls": [{"stat": stat, "sign": sign, "checks": stats["checks"], "procs": stats["procs"],
                   "rate": _percent(stats["procs"], stats["checks"]), "avg_streak": _average(stats["streak"], stats["procs"])}
                  for stat in ("luck", "morale") for sign in ("positive", "negative") for stats in [rolls[stat, sign]]],
        "summons": dict(sorted(summons.items())),
    }
    return combat, hunting, effects, recent, volumes


def _players(db, start, now):
    levels = dict(db.execute(select(func.coalesce(User.level, 1), func.count(User.id))
                              .where(User.is_system.is_(False)).group_by(func.coalesce(User.level, 1))).all())
    active = db.scalar(select(func.count(User.id)).where(
        User.is_system.is_(False), User.is_active.is_(True), *_range(User.last_seen_at, start, now)))
    sessions = dict(db.execute(select(Battle.status, func.count(Battle.id)).where(
        Battle.status.in_(("active", "deployment"))).group_by(Battle.status)).all())
    return {"registered": sum(levels.values()), "active": active, "levels": dict(sorted(levels.items())),
            "sessions": {key: sessions.get(key, 0) for key in ("active", "deployment")}}


def dashboard(db, period, limit=20, *, now=None):
    now = now or datetime.now(UTC).replace(tzinfo=None)
    start = now - PERIODS[period] if PERIODS[period] else None
    hourly = period == "24h"
    step = timedelta(hours=1) if hourly else timedelta(days=1)

    def bucket(moment):
        return moment.replace(hour=moment.hour if hourly else 0, minute=0, second=0, microsecond=0)

    integrity, items = catalog_integrity()
    resources = {key: row["name"] for key, row in resource_definitions().items()}
    combat, hunting, effects, recent, battles = _combat(db, start, now, bucket, limit)
    shop, economy, flows = _economy(db, start, now, bucket, resources, items)
    players = _players(db, start, now)
    current = bucket(start) if start else min((*battles, *flows), default=bucket(now))
    battle_series, economy_series = [], []
    while current <= bucket(now):
        stamp = _timestamp(current)
        outcomes = battles.get(current, Counter())
        battle_series.append({"bucket": stamp, "total": outcomes.total(), **{key: outcomes[key] for key in OUTCOMES}})
        economy_series.append({"bucket": stamp, **_flow_row(flows.get(current, {}), resources)})
        current += step
    return {
        "period": period, "generated_at": _timestamp(now), "combat": combat, "hunting": hunting, "effects": effects,
        "shop": shop, "economy": economy, "players": players, "replays": recent, "integrity": integrity,
        "labels": {"resources": resources, "categories": CATEGORIES},
        "tracking_started_at": _timestamp(first_event) if (
            first_event := db.scalar(select(func.min(GameplayEvent.occurred_at)))) else None,
        "series": {
            "granularity": "hourly" if hourly else "daily", "battles": battle_series, "economy": economy_series,
            "breakdowns": {"hero_levels": _labels(players["levels"].items()),
                           "top_items": _labels((row["name"], row["count"]) for row in shop["top"]),
                           "categories": _labels((CATEGORIES.get(key, key), count) for key, count in shop["categories"].items())},
        },
    }
