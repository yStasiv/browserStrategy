"""Configurable experience tables for heroes and guilds."""
import json
from functools import lru_cache
from pathlib import Path

TABLE_FILE = Path(__file__).resolve().parents[2] / "content" / "experience_tables.json"


@lru_cache(maxsize=1)
def tables():
    data = json.loads(TABLE_FILE.read_text(encoding="utf-8"))
    hero = {int(key): value for key, value in data["hero"].items()}
    default = {int(key): value for key, value in data["default"].items()}
    guilds = {guild: {int(key): value for key, value in rows.items()} for guild, rows in data["guilds"].items()}
    growth = data["per_level_after_table"]
    if (not default or set(default) != set(range(max(default) + 1))
            or type(growth) is not int or growth < 0
            or any(level < 0 or type(value) is not int or value <= 0
                   for table in (default, *guilds.values()) for level, value in table.items())):
        raise ValueError("Перевір рівні та додатні пороги в experience_tables.json.")
    ordered = sorted(hero)
    if (ordered != list(range(1, len(hero) + 1))
            or any(type(value) is not int or value <= 0 for value in hero.values())
            or any(hero[level] >= hero[level + 1] for level in ordered[:-1])):
        raise ValueError("Пороги досвіду героя мають зростати послідовно з 1-го рівня.")
    return default, guilds, growth, hero


def xp_threshold(level, guild="adventurers"):
    default, guilds, growth, _ = tables()
    last = max(default)
    return guilds.get(guild, {}).get(level, default[min(level, last)] + max(0, level - last) * growth)


def hero_xp_threshold(level: int) -> int | None:
    """Return total experience needed to reach the next hero level."""
    return tables()[3].get(level)
