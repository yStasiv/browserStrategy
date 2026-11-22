"""Battle creature catalog and existing PvE scenarios."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Recruitment:
    factions: list[str]
    min_level: int
    max_count: int
    building: str


@dataclass(frozen=True)
class Hunting:
    min_level: int
    count: int
    difficulty: str


@dataclass(frozen=True)
class UnitType:
    key: str
    name: str
    attack: int
    defense: int
    dmg_min: int
    dmg_max: int
    hp: int
    speed: int
    initiative: int
    shots: int
    size: tuple[int, int]
    icon: str
    abilities: tuple[str, ...]
    starter_count: int
    recruitment: Recruitment | None
    hunting: Hunting | None
    recruitment_points: int
    description: str = ""
    image_url: str | None = None
    luck: int = 0
    morale: int = 0
    knowledge: int = 0


def load_creatures():
    path = Path(__file__).resolve().parents[2] / "content" / "creatures.json"
    catalog = {}
    for row in json.loads(path.read_text(encoding="utf-8")):
        recruit, hunt = row.pop("recruitment"), row.pop("hunting")
        row["size"] = tuple(row["size"])
        row["abilities"] = tuple(row["abilities"])
        unit = UnitType(**row, recruitment=Recruitment(**recruit) if recruit else None,
                        hunting=Hunting(**hunt) if hunt else None)
        if (unit.key in catalog or len(unit.size) != 2 or min(*unit.size, unit.hp, unit.initiative) < 1
                or not 1 <= unit.dmg_min <= unit.dmg_max or not 0 <= unit.initiative <= 100_000
                or min(unit.speed, unit.shots, unit.starter_count) < 0
                or type(unit.recruitment_points) is not int or unit.recruitment_points < 0
                or (unit.hunting and min(unit.hunting.min_level, unit.hunting.count) < 1)
                or (unit.recruitment and (
                    not unit.recruitment.building or min(unit.recruitment.min_level, unit.recruitment.max_count) < 1
                ))
                or set(unit.abilities) != ({"ranged_attack"} if unit.shots else set())):
            raise ValueError(f"Некоректні параметри істоти: {unit.key}")
        catalog[unit.key] = unit
    return catalog


UNITS = load_creatures()
DEFAULT_ARMY = [(u.key, u.starter_count) for u in UNITS.values() if u.starter_count]
UNIT_PRESENTATION = {u.key: {"name": u.name, "emoji": u.icon} for u in UNITS.values()}


# PvE-сценарії (поки тут; пізніше переїдуть у БД/конфіг разом із нагородами та складністю)
PVE_SCENARIOS = {
    "training": {"title": "Тренувальний бій", "min_level": 1,
                 "army": [("goblin", 12), ("skeleton", 6)]},
    "ruins": {"title": "Руїни", "min_level": 1,
              "army": [("skeleton", 20), ("archer", 8), ("goblin", 10)]},
    "ogres": {"title": "Лігво огрів", "min_level": 1,
              "army": [("ogre", 2), ("goblin", 10)]},
    "dragon_lair": {"title": "Лігво дракона", "min_level": 4,
                    "army": [("dragon", 1), ("ogre", 2), ("skeleton", 15)]},
}
