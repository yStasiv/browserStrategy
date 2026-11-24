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


def level_limits(guild):
    if guild.startswith("metalworking:"):
        return 0, MAX_METALWORKING_LEVEL
    return 1, MAX_COLLEGE_LEVEL if guild == METALWORKERS else None


def spent_points(guild, level):
    starting_level, _ = level_limits(guild)
    return sum(xp_threshold(previous, guild) for previous in range(starting_level, level))


def award_point(db, player_id, guild, points=1):
    if points <= 0:
        return
    starting_level, max_level = level_limits(guild)
    if not insert_once(db, ActivityGuildProgress, player_id=player_id, guild=guild,
                       points=points, level=starting_level):
        db.execute(
            update(ActivityGuildProgress)
            .where(ActivityGuildProgress.player_id == player_id, ActivityGuildProgress.guild == guild)
            .values(points=ActivityGuildProgress.points + points)
        )
    row = db.get(ActivityGuildProgress, (player_id, guild), populate_existing=True)
    level = row.level if row.level is not None else starting_level
    if level != max_level and row.points >= spent_points(guild, level) + xp_threshold(level, guild):
        row.level = level + 1
        db.flush([row])


def progress(db, player_id, guild):
    row = db.get(ActivityGuildProgress, (player_id, guild))
    return level_progress(row, guild)


def workshop_progress(db, player_id):
    return {
        key: level_progress(row, workshop_key(key))
        for key in WORKSHOPS
        if (row := db.get(ActivityGuildProgress, (player_id, workshop_key(key)))) is not None
    }


def workshop_key(key):
    return f"metalworking:{key}"


def display_points(points):
    rounded = Decimal(points).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return int(rounded) if rounded == int(rounded) else rounded


def level_progress(row, guild):
    starting_level, max_level = level_limits(guild)
    level = row.level if row is not None and row.level is not None else starting_level
    points = max(0, row.points - spent_points(guild, level)) if row is not None else 0
    threshold = None if level == max_level else xp_threshold(level, guild)
    return {"level": level, "xp": display_points(points), "next_xp": threshold}


def repair_percent(level):
    return min(95, max(5, level * 10))
