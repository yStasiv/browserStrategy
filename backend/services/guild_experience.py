"""Configurable experience tables for heroes and guilds."""
import json
from functools import lru_cache
from pathlib import Path

from backend.services.resource_balances import resource_definitions

TABLE_FILE = Path(__file__).resolve().parents[2] / "content" / "experience_tables.json"


@lru_cache(maxsize=1)
def tables():
    data = json.loads(TABLE_FILE.read_text(encoding="utf-8"))
    leveling = {int(key): row for key, row in data["hero_leveling"].items()}
    hero = {level: row["exp"] for level, row in leveling.items()}
    default = {int(key): value for key, value in data["default"].items()}
    guilds = {guild: {int(key): value for key, value in rows.items()} for guild, rows in data["guilds"].items()}
    growth = data["per_level_after_table"]
    if (not default or set(default) != set(range(max(default) + 1))
            or type(growth) is not int or growth < 0
            or any(level < 0 or type(value) is not int or value <= 0
                   for table in (default, *guilds.values()) for level, value in table.items())):
        raise ValueError("Перевір рівні та додатні пороги в experience_tables.json.")
    ordered = sorted(hero)
    if (ordered != list(range(2, len(hero) + 2))
            or any(type(value) is not int or value <= 0 for value in hero.values())
            or any(hero[level] >= hero[level + 1] for level in ordered[:-1])):
        raise ValueError("Пороги досвіду героя мають зростати послідовно з 2-го рівня.")
    rewards = {level: row["rewards"] for level, row in leveling.items()}
    resources = resource_definitions()
    for reward in rewards.values():
        if (not isinstance(reward, dict)
                or any(resource not in resources or type(amount) is not int or amount < 0
                       for resource, amount in reward.items())):
            raise ValueError("Перевір нагороди за рівні героя в experience_tables.json.")
    return default, guilds, growth, hero, rewards


def xp_threshold(level, guild="adventurers"):
    default, guilds, growth, _, _ = tables()
    last = max(default)
    return guilds.get(guild, {}).get(level, default[min(level, last)] + max(0, level - last) * growth)


def hero_xp_threshold(level: int) -> int | None:
    """Return total experience needed to reach the next hero level."""
    return tables()[3].get(level + 1)


def hero_level_reward(level: int) -> dict[str, int]:
    """Return the resources awarded for reaching this level."""
    return tables()[4].get(level, {})
