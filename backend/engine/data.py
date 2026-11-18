"""Довідник істот. Цифри — заглушки для тестів, баланс виносимо в БД/конфіг пізніше."""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class UnitType:
    key: str
    name: str
    attack: int
    defense: int
    dmg_min: int
    dmg_max: int
    hp: int
    speed: int        # скільки клітинок за хід
    initiative: int   # чим більше, тим частіше й раніше діє
    shots: int = 0    # 0 = ближній бій; >0 = стрілець із боєзапасом
    size: Tuple[int, int] = (1, 1)   # (ширина, висота) у клітинках


UNITS = {u.key: u for u in [
    UnitType("peasant",   "Селянин",  1,  1, 1, 1,  4, 3,  9),
    UnitType("archer",    "Лучник",   6,  3, 2, 3, 10, 4, 10, shots=12),
    UnitType("swordsman", "Мечник",  10, 12, 6, 9, 35, 4, 10),
    UnitType("knight",    "Лицар",   16, 12, 15, 25, 90, 5, 8),
    UnitType("goblin",    "Гоблін",   4,  2, 1, 2,  5, 5, 9),
    UnitType("skeleton",  "Скелет",   5,  4, 1, 3,  6, 4, 8),
    # великі істоти (ширина x висота); цифри — заглушки
    UnitType("ogre",      "Огр",     13,  9, 8, 14, 60, 4, 7, size=(2, 2)),
    UnitType("dragon",    "Дракон",  20, 18, 40, 60, 180, 5, 9, size=(2, 3)),
]}

# Армія нового персонажа: (тип, кількість), максимум 8 слотів (на низьких рівнях у PvE — 5, див. setup.field_rules)
DEFAULT_ARMY = [("peasant", 20), ("archer", 10), ("swordsman", 5)]


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
