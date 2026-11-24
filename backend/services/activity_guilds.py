from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import update

from backend.guild_models import ActivityGuildProgress
from backend.services.guild import insert_once, xp_threshold


HUNTERS = "hunters"
WORKERS = "workers"
METALWORKERS = "metalworkers"
MAX_METALWORKING_LEVEL = 10
MAX_COLLEGE_LEVEL = 4
WORKSHOPS = {
    "jewelry": ("Ювелірна справа", ("jewelry",)),
    "forge": ("Кузня", ("one_handed_weapon", "two_handed_weapon", "bow")),
    "armor": ("Майстерня обладунків", ("helmet", "armor", "boots", "back", "shield")),
    "enchanting": ("Зачарувальня", ()),
}
WORKSHOP_ICONS = {
    "jewelry": "/static/images/guild_icons/workshop_jewelry.png",
    "forge": "/static/images/guild_icons/workshop_weapons.png",
    "armor": "/static/images/guild_icons/workshop_armor.png",
    "enchanting": "/static/images/guild_icons/workshop_enchanting.png",
}


def award_point(db, player_id, guild, points=1):
    if not points:
        return
    if not insert_once(db, ActivityGuildProgress, player_id=player_id, guild=guild, points=points):
        db.execute(
            update(ActivityGuildProgress)
            .where(ActivityGuildProgress.player_id == player_id, ActivityGuildProgress.guild == guild)
            .values(points=ActivityGuildProgress.points + points)
        )


def progress(db, player_id, guild):
    row = db.get(ActivityGuildProgress, (player_id, guild))
    return level_progress(row.points if row else 0, 1, MAX_COLLEGE_LEVEL if guild == METALWORKERS else None, guild)


def workshop_progress(db, player_id):
    return {
        key: level_progress(row.points, 0, MAX_METALWORKING_LEVEL, workshop_key(key))
        for key in WORKSHOPS
        if (row := db.get(ActivityGuildProgress, (player_id, workshop_key(key)))) is not None
    }


def workshop_key(key):
    return f"metalworking:{key}"


def display_points(points):
    rounded = Decimal(points).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return int(rounded) if rounded == int(rounded) else rounded


def level_progress(points, level, max_level, guild):
    threshold = xp_threshold(level, guild)
    while points >= threshold and level != max_level:
        points -= threshold
        level += 1
        threshold = xp_threshold(level, guild)
    if level == max_level:
        return {"level": level, "xp": display_points(points), "next_xp": None, "remaining_xp": None}
    return {"level": level, "xp": display_points(points), "next_xp": threshold, "remaining_xp": display_points(threshold - points)}


def repair_percent(level):
    return min(95, max(5, level * 10))
