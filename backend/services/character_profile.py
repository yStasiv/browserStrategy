import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import LEGACY_BALANCES, RESOURCE_FILE

from backend.engine.battle_models import Battle, BattleParticipant
from backend.engine.data import UNITS, faction_key
from backend.engine.hero import hero_portrait_url
from backend.engine.roster import saved_army
from backend.engine.battle_service import user_level
from backend.engine.setup import field_rules
from backend.services.hero_army import army_options
from backend.services.combat_effects import EFFECT_LABELS, active_combat_effects, artifact_bonus_rows
from backend.services.hero_attributes import PROFILE_STATS, hero_attributes
from backend.services.hero_equipment import ITEM_SLOTS, SLOT_LABELS, equipment_ids, hand_conflict
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
STAT_LABELS.update(EFFECT_LABELS)
STAT_LABELS.update({column: name for name, column, _ in PROFILE_STATS.values()})
FACTIONS = {"elves": "Ельфи", "underground_elves": "Підземні ельфи", "system": "Системна"}
GENDERS = {"male": "Чоловік", "female": "Жінка"}
EQUIPMENT_MODELS = {
    "elves": {"male": "elves_male_back_model.png.png", "female": "elves_woman_back_model.png"},
    "underground_elves": {"male": "underground_elves_male_back_model.png", "female": "underground_elves_woman_back_model.png"},
}


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
    level, xp = (progress.level, progress.xp) if progress else (1, 0)
    threshold = xp_threshold(level)
    return {"level": level, "xp": xp, "next_xp": threshold}


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
    Service("battle_history", "Історія боїв", "/battle/history", 40),
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


def equipment_state(db, player):
    ids = equipment_ids(player.equipped_items)
    owned = db.scalars(select(Item).where(Item.owner_id == player.id).order_by(Item.id)).all()
    items = {item.id: item for item in owned}
    equipped = {item_id: items[item_id] for item_id in set(ids.values()) if item_id in items}
    main = equipped.get(ids["main_hand"])

    attributes = hero_attributes(player, equipped.values())
    for key, stat in attributes.items():
        stat["image_url"] = stat_icon_url(key)

    equipment = {}
    for slot, name in SLOT_LABELS.items():
        item = equipped.get(ids[slot])
        equipment[slot] = {
            "name": name,
            "item": {"id": item.id, "name": item.name, "image_url": item.image_url,
                     "item_type": item.item_type, "durability": item.durability, "max_durability": item.max_durability,
                     "description": item.description,
                     "bonuses": artifact_bonus_rows(item.stats, STAT_LABELS)} if item else None,
            "choices": [{"id": candidate.id, "name": candidate.name} for candidate in owned
                        if ids[slot] is None and candidate.id not in equipped and slot in ITEM_SLOTS.get(candidate.item_type, ())
                        and not hand_conflict(candidate.item_type, slot, ids, main.item_type if main else None)
                        and (candidate.durability is None or candidate.durability > 0)],
        }
    return attributes, equipment, owned


def hero_state(db, player):
    attributes, equipment, owned = equipment_state(db, player)
    ids = set(equipment_ids(player.equipped_items).values())
    effects = active_combat_effects(item for item in owned if item.id in ids)
    options = army_options(db, player)
    roster = saved_army(db, player.id)
    squads = [{"key": key, "name": UNITS[key].name, "icon": UNITS[key].icon, "unit": UNITS[key], "count": count}
              for key, count in roster if key in UNITS]
    limit = field_rules(user_level(player), "pve").max_slots
    return {"attributes": attributes, "equipment": equipment,
            "active_effects": [(EFFECT_LABELS[key], value) for key, value in effects.items()],
            "effects_icon": stat_icon_url("active_effects"),
            "army": {"squads": squads, "spent": len(squads), "available": limit,
                     "free": max(0, limit - len(squads)), "options": options}}


def equipment_model_url(faction, gender):
    model_faction = faction if faction in EQUIPMENT_MODELS else "elves"
    equipment_model = EQUIPMENT_MODELS[model_faction][gender]
    return f"/static/images/units_and_buildings/{model_faction}/hero/{equipment_model}"


def dashboard(db, player, next_level_exp):
    faction = faction_key(player.fraction)
    gender = player.gender or "male"
    recent = db.execute(select(Battle.id, Battle.winner_side, BattleParticipant.side)
                        .join(BattleParticipant, BattleParticipant.battle_id == Battle.id)
                        .where(BattleParticipant.user_id == player.id, Battle.status == "finished")
                        .order_by(Battle.id.desc()).limit(1)).first()
    return {
        "resources": resources(db, player), **hero_state(db, player),
        "reset_stat_icon": stat_icon_url("reset"),
        "next_level_exp": next_level_exp,
        "faction": FACTIONS.get(faction, player.fraction),
        "faction_key": faction,
        "gender": GENDERS[gender],
        "portrait_url": hero_portrait_url(faction, gender),
        "equipment_model_url": equipment_model_url(faction, gender),
        "guilds": progress_entries(db, player, GUILDS),
        "faction_skills": progress_entries(db, player, FACTION_SKILLS),
        "services": [service for service in sorted(SERVICES, key=lambda service: service.order)
                     if service.route and (service.available is None or service.available(player))],
        "recent": recent,
    }
