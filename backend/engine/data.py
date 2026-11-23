"""Battle creature catalog and existing PvE scenarios."""
import json
from dataclasses import dataclass
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[2] / "content"
FACTION_ROSTERS = json.loads((CONTENT / "faction_creatures.json").read_text(encoding="utf-8"))
SUMMONING = json.loads((CONTENT / "elemental_summoning.json").read_text(encoding="utf-8"))
ELEMENTALS = {row["element"]: row for row in SUMMONING["elementals"]}
DEFAULT_SHOOTING_RANGE = 6


def faction_key(value):
    key = (value or "").casefold()
    return {"elfe": "elves", "darkelfe": "underground_elves", "undergroundelves": "underground_elves"}.get(key, key)


@dataclass(frozen=True)
class Recruitment:
    factions: list[str]
    min_level: int
    max_count: int
    building: str


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
    recruitment_points: int
    description: str = ""
    image_url: str | None = None
    luck: int = 0
    morale: int = 0
    knowledge: int = 0
    shooting_range: int = DEFAULT_SHOOTING_RANGE
    faction: str | None = None
    tier: int | None = None
    form: int | None = None
    line: str | None = None
    element: str | None = None
    skills: tuple[str, ...] = ()


def creature_rows():
    yield from json.loads((CONTENT / "creatures.json").read_text(encoding="utf-8"))
    for faction, roster in FACTION_ROSTERS.items():
        if sorted(line["tier"] for line in roster) != list(range(1, 9)):
            raise ValueError(f"Фракція має містити вісім рангів: {faction}")
        for line in roster:
            if sorted(form["form"] for form in line["forms"]) != [1, 2, 3]:
                raise ValueError(f"Лінійка має містити три форми: {line['key']}")
            for form in line["forms"]:
                key = f"{faction}_{line['key']}_{form['form']}"
                recruitment = line["recruitment"]
                if recruitment:
                    recruitment = {
                        **recruitment, "factions": [faction],
                        "building": form.get("building", recruitment["building"]),
                    }
                yield {
                    **{key: value for key, value in form.items() if key != "building"},
                    "key": key, "tier": line["tier"], "faction": faction,
                    "line": f"{faction}_{line['key']}", "icon": line["icon"],
                    "speed": line["speed"], "shots": line["shots"], "abilities": line["abilities"],
                    "shooting_range": form.get("shooting_range", line.get("shooting_range", DEFAULT_SHOOTING_RANGE)),
                    "size": line.get("size", (1, 1)), "starter_count": 0,
                    "recruitment": recruitment,
                    "recruitment_points": form["army_points_cost"],
                }
    for element, row in ELEMENTALS.items():
        yield {
            **{key: value for key, value in row.items() if key != "school_level"},
            "key": f"elemental_{element}", "size": (1, 1), "starter_count": 0,
            "recruitment": None, "recruitment_points": 0,
        }


def load_creatures():
    catalog = {}
    for row in creature_rows():
        recruit = row.pop("recruitment")
        row.pop("army_points_cost", None)
        row["size"] = tuple(row["size"])
        row["abilities"] = tuple(row["abilities"])
        if "skills" in row:
            row["skills"] = tuple(row["skills"])
        unit = UnitType(**row, recruitment=Recruitment(**recruit) if recruit else None)
        if (unit.key in catalog or len(unit.size) != 2 or min(*unit.size, unit.hp, unit.initiative) < 1
                or not 1 <= unit.dmg_min <= unit.dmg_max or not 0 <= unit.initiative <= 100_000
                or min(unit.speed, unit.shots, unit.starter_count) < 0
                or type(unit.shooting_range) is not int or unit.shooting_range < 1
                or type(unit.recruitment_points) is not int or unit.recruitment_points < 0
                or (unit.recruitment and (
                    not unit.recruitment.building or min(unit.recruitment.min_level, unit.recruitment.max_count) < 1
                ))
                or set(unit.abilities) != ({"ranged_attack"} if unit.shots else set())):
            raise ValueError(f"Некоректні параметри істоти: {unit.key}")
        catalog[unit.key] = unit
    return catalog


UNITS = load_creatures()
UNIT_PRESENTATION = {u.key: {"name": u.name, "emoji": u.icon} for u in UNITS.values()}
for unit in UNITS.values():
    if unit.image_url:
        UNIT_PRESENTATION[unit.key]["image_url"] = unit.image_url
    if unit.form is not None:
        UNIT_PRESENTATION[unit.key].update(tier=unit.tier, form=unit.form, faction=unit.faction)
    if unit.element is not None:
        UNIT_PRESENTATION[unit.key].update(element=unit.element, hp=unit.hp)


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
