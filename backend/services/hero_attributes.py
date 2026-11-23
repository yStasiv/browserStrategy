"""The effective attributes displayed in the profile and copied into combat."""
import json

from backend.engine.data import CONTENT
from backend.engine.state import ATB_SCALE


HERO_RULES = json.loads((CONTENT / "battle_hero.json").read_text(encoding="utf-8"))
if not 1 <= HERO_RULES["initiative"] <= ATB_SCALE or not 1 <= HERO_RULES["damage_min"] <= HERO_RULES["damage_max"]:
    raise ValueError("Некоректна ініціатива або діапазон шкоди героя.")

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


def hero_attributes(player, equipped):
    attributes = {}
    for key, (name, column, icon) in PROFILE_STATS.items():
        bonus = sum(
            value for item in equipped if type(value := (item.stats or {}).get(column, 0)) in (int, float)
        )
        base = (getattr(player, column) or 0) - bonus if hasattr(player, column) else 0
        if key == "initiative":
            base += HERO_RULES["initiative"]
        total = base + bonus
        if key == "initiative":
            total = max(1, min(ATB_SCALE, int(total)))
        attributes[key] = {
            "name": name, "icon": icon, "base": base, "equipment": bonus,
            "buildings": 0, "total": total, "spendable": key in SPENDABLE_ATTRIBUTES,
        }
    return attributes
