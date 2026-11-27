"""Percentage combat modifiers supplied by equipped items and other bonuses."""

EFFECT_LABELS = {
    "ranged_damage_boost": "Підсилення дальніх атак",
    "shot_protection": "Захист від пострілів",
    "ignore_attack": "Ігнорування атаки",
    "ignore_defense": "Ігнорування захисту",
}


def active_combat_effects(equipped, *bonuses):
    sources = [item.stats or {} for item in equipped if item.durability is None or item.durability > 0]
    sources.extend(bonuses)
    result = {}
    for key in EFFECT_LABELS:
        value = min(100, sum(amount for source in sources
                             if type(amount := source.get(key)) in (int, float) and amount > 0))
        if value:
            result[key] = value
    return result



def artifact_bonus_rows(stats, labels):
    return [(labels[key], value, key in EFFECT_LABELS)
            for key, value in (stats or {}).items()
            if key in labels and type(value) in (int, float) and value]
