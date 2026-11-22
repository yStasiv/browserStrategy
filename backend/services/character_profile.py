import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import LEGACY_BALANCES, RESOURCE_FILE

from backend.engine.battle_models import Battle, BattleParticipant
from backend.engine.data import UNITS, faction_key
from backend.engine.roster import saved_army
from backend.engine.battle_service import user_level
from backend.engine.setup import field_rules
from backend.services.hero_army import army_options
from backend.services.hero_equipment import ITEM_SLOTS, SLOT_LABELS, equipment_ids
from backend.guild_models import GuildProgress
from backend.models import Item, PlayerResourceBalance, User
from backend.services.guild import xp_threshold
from backend.services import activity_guilds

STAT_ICON_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static" / "images" / "hero_stats"

ATTRIBUTES = {"stamina": "Витривалість", "energy": "Енергія", "agility": "Спритність", "mind": "Розум"}
COMBAT_STATS = {
    "melee_attack": "Ближня атака", "ranged_attack": "Дальня атака", "magic_power": "Магічна сила",
    "physical_defense": "Фізичний захист", "magic_resistance": "Опір магії",
    "bonus_melee_damage": "Бонус ближньої шкоди", "bonus_ranged_damage": "Бонус дальньої шкоди",
    "bonus_magic_damage": "Бонус магічної шкоди", "bonus_melee_defense": "Бонус захисту в ближньому бою",
    "bonus_ranged_defense": "Бонус захисту від стрільби", "bonus_magic_defense": "Бонус захисту від магії",
}
STAT_LABELS = ATTRIBUTES | COMBAT_STATS
PROFILE_STATS = {
    "attack": ("Атака", "melee_attack", "⚔"),
    "defense": ("Захист", "physical_defense", "🛡"),
    "spell_power": ("Сила магії", "magic_power", "✦"),
    "knowledge": ("Знання", "mind", "📖"),
    "luck": ("Удача", "luck", "☘"),
    "morale": ("Бойовий дух", "morale", "⚑"),
    "initiative": ("Ініціатива", "initiative", "⌛"),
}
SPENDABLE_ATTRIBUTES = {
    key: PROFILE_STATS[key][1] for key in ("attack", "defense", "spell_power", "knowledge")
}
STAT_LABELS.update({column: name for name, column, _ in PROFILE_STATS.values()})
FACTIONS = {"elves": "Ельфи", "underground_elves": "Темні ельфи", "admin": "Адміністрація", "system": "Системна"}


def resources(db, player):
    catalog = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
    permanent = catalog["permanent"]
    unique = catalog["unique"]
    configured_ids = {row["id"] for row in permanent}
    if len(permanent) != 6 or len(configured_ids) != 6 or unique["id"] in configured_ids:
        raise ValueError("Каталог має містити шість різних постійних ресурсів і один умовний.")
    ids = (configured_ids | {unique["id"]}) - LEGACY_BALANCES
    values = dict(db.execute(select(PlayerResourceBalance.resource_id, PlayerResourceBalance.quantity).where(
        PlayerResourceBalance.player_id == player.id, PlayerResourceBalance.resource_id.in_(ids)
    )).all())
    values.update({key: getattr(player, key) or 0 for key in LEGACY_BALANCES})
    visible = list(permanent)
    if unique.get("active") and unique.get("name") and (values.get(unique["id"]) or 0) > 0:
        visible.append(unique)
    return [
        {**row, "conditional": row is unique, "quantity": values.get(row["id"], 0) or 0}
        for row in visible
    ]


@dataclass(frozen=True)
class ProgressFeature:
    id: str
    name: str
    data: Callable[[Session, User], dict | None]
    icon: str | None = None
    description: str | None = None
    requirements: str | None = None
    route: str | None = None


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    route: str | None
    order: int
    icon: str | None = None
    requirements: str | None = None
    available: Callable[[User], bool] | None = None


def adventurers_progress(db, player):
    progress = db.get(GuildProgress, player.id)
    level, xp, threshold = (progress.level, progress.xp, progress.next_xp) if progress else (1, 0, xp_threshold(1))
    return {"level": level, "xp": xp, "next_xp": threshold, "remaining_xp": max(0, threshold - xp)}


def metalworking_progress(db, player):
    progress = activity_guilds.progress(db, player.id, activity_guilds.METALWORKERS)
    unlocked = activity_guilds.workshop_progress(db, player.id)
    return {
        **progress,
        "workshops": [
            {"name": name, "icon": activity_guilds.WORKSHOP_ICONS[key], "progress": unlocked.get(key)}
            for key, (name, _) in activity_guilds.WORKSHOPS.items()
        ],
    }


GUILDS = (
    ProgressFeature("adventurers", "Гільдія авантюристів", adventurers_progress,
                    icon="/static/images/guild_icons/guild_adventurers.png"),
    ProgressFeature(activity_guilds.HUNTERS, "Братство ловців",
                    lambda db, player: activity_guilds.progress(db, player.id, activity_guilds.HUNTERS),
                    icon="/static/images/guild_icons/guild_hunters.png"),
    ProgressFeature(activity_guilds.WORKERS, "Спілка трудівників",
                    lambda db, player: activity_guilds.progress(db, player.id, activity_guilds.WORKERS),
                    icon="/static/images/guild_icons/guild_workers.png"),
    ProgressFeature(activity_guilds.METALWORKERS, "Колегія металознавців", metalworking_progress,
                    icon="/static/images/guild_icons/guild_metallurgists.png"),
)
FACTION_SKILLS: tuple[ProgressFeature, ...] = ()
SERVICES = (
    Service("inventory", "Інвентар", "/inventory", 10),
    Service("shop", "Магазин артефактів", "/shop", 20),
    Service("battle", "Почати бій", "/battle", 30),
    Service("battle_history", "Історія боїв", "/battle/history", 40),
    Service("quests", "Журнал завдань", "/char_tasks", 50),
    Service("help", "Довідка по грі", "/help", 60),
)


def progress_entries(db, player, registry):
    entries = []
    for feature in registry:
        progress = feature.data(db, player)
        if progress is None:
            continue
        entries.append({
            "id": feature.id, "name": feature.name, "icon": feature.icon,
            "description": feature.description, "requirements": feature.requirements,
            "route": feature.route if progress.get("available") else None,
            **progress,
        })
    return entries


def stat_icon_url(key):
    icon_file = f"{key}.png"
    return f"/static/images/hero_stats/{icon_file}" if (STAT_ICON_DIR / icon_file).is_file() else None


def hero_state(db, player):
    ids = equipment_ids(player.equipped_items)
    owned = db.scalars(select(Item).where(Item.owner_id == player.id).order_by(Item.id)).all()
    items = {item.id: item for item in owned}
    equipped = {item_id: items[item_id] for item_id in set(ids.values()) if item_id in items}

    attributes = {}
    for key, (name, column, icon) in PROFILE_STATS.items():
        bonus = sum((item.stats or {}).get(column, 0) for item in equipped.values()
                    if isinstance((item.stats or {}).get(column, 0), (int, float)))
        stored = getattr(player, column, None)
        base = (stored or 0) - bonus if hasattr(player, column) else 0
        attributes[key] = {"name": name, "icon": icon, "image_url": stat_icon_url(key), "base": base, "equipment": bonus,
                           "buildings": 0, "total": base + bonus, "spendable": key in SPENDABLE_ATTRIBUTES}

    equipment = {}
    for slot, name in SLOT_LABELS.items():
        item = equipped.get(ids[slot])
        equipment[slot] = {
            "name": name,
            "item": {"id": item.id, "name": item.name, "image_url": item.image_url,
                     "description": item.description,
                     "bonuses": [(STAT_LABELS[k], v)
                                 for k, v in (item.stats or {}).items()
                                 if k in STAT_LABELS and isinstance(v, (int, float)) and v]} if item else None,
            "choices": [{"id": candidate.id, "name": candidate.name} for candidate in owned
                        if candidate.id not in equipped and slot in ITEM_SLOTS.get(candidate.item_type, ())
                        and (candidate.durability is None or candidate.durability > 0)],
        }

    options = army_options(db, player)
    roster = saved_army(db, player.id)
    squads = [{"key": key, "name": UNITS[key].name, "icon": UNITS[key].icon, "unit": UNITS[key], "count": count}
              for key, count in roster if key in UNITS]
    limit = field_rules(user_level(player), "pve").max_slots
    return {"attributes": attributes, "equipment": equipment,
            "army": {"squads": squads, "spent": len(squads), "available": limit,
                     "free": max(0, limit - len(squads)), "options": options}}


def dashboard(db, player, next_level_exp):
    recent = db.execute(select(Battle.id, Battle.winner_side, BattleParticipant.side)
                        .join(BattleParticipant, BattleParticipant.battle_id == Battle.id)
                        .where(BattleParticipant.user_id == player.id, Battle.status == "finished")
                        .order_by(Battle.id.desc()).limit(1)).first()
    return {
        "resources": resources(db, player), **hero_state(db, player),
        "reset_stat_icon": stat_icon_url("reset"),
        "next_level_exp": next_level_exp,
        "faction": FACTIONS.get(faction_key(player.fraction), player.fraction),
        "faction_key": faction_key(player.fraction),
        "guilds": progress_entries(db, player, GUILDS),
        "faction_skills": progress_entries(db, player, FACTION_SKILLS),
        "services": [service for service in sorted(SERVICES, key=lambda service: service.order)
                     if service.route and (service.available is None or service.available(player))],
        "recent": recent,
    }
