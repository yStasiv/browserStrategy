"""Hunt catalog and reproducible per-player offers based on settled battles."""
from datetime import timedelta
from random import Random

from pydantic import BaseModel, ConfigDict, PositiveInt, TypeAdapter
from sqlalchemy import case, func, select

from .battle_models import Battle, BattleParticipant
from .data import CONTENT, UNITS


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creature: str
    base_count: PositiveInt
    count_per_level: PositiveInt
    min_level: PositiveInt


def load_targets():
    rows = TypeAdapter(list[Target]).validate_json((CONTENT / "hunting_targets.json").read_text(encoding="utf-8"))
    targets = {row.creature: row for row in rows}
    if len(targets) != len(rows) or targets.keys() - UNITS.keys():
        raise ValueError("Каталог полювання містить невідомі або повторені ключі істот.")
    return targets


TARGETS = load_targets()


def ready_at(db, player_id, now):
    finish = db.execute(select(Battle.finished_at, Battle.winner_side, BattleParticipant.side)
                        .join(BattleParticipant, BattleParticipant.battle_id == Battle.id)
                        .where(BattleParticipant.user_id == player_id, Battle.status == "finished",
                               Battle.finished_at > now - timedelta(seconds=60),
                               Battle.state["hunt_key"].as_string().is_not(None))
                        .order_by(Battle.finished_at.desc(), Battle.id.desc()).limit(1)).first()
    if finish is None:
        return None
    deadline = finish.finished_at + timedelta(seconds=60 if finish.winner_side == finish.side else 30)
    return deadline if deadline > now else None


def offers(db, player_id, level):
    key = Battle.state["hunt_key"].as_string()
    history = db.execute(select(
        key, func.max(Battle.id),
        func.sum(case((Battle.winner_side == BattleParticipant.side, 1), else_=0)),
    ).join(BattleParticipant, BattleParticipant.battle_id == Battle.id).where(
        BattleParticipant.user_id == player_id, Battle.status == "finished",
        Battle.rewarded.is_(True), key.is_not(None),
    ).group_by(key)).all()
    victories = {creature: wins for creature, _, wins in history}
    latest_battle = max((battle_id for _, battle_id, _ in history), default=None)

    unlocked = [target for target in TARGETS.values() if target.min_level <= level]
    Random(f"{player_id}:{latest_battle or 0}").shuffle(unlocked)
    return [
        (target, 1 + victories.get(target.creature, 0))
        for target in unlocked[:2]
    ]


def squad_count(target, difficulty):
    # Each new difficulty adds a percentage of the base squad, without compounding.
    percent = 100 + (difficulty - 1) * target.count_per_level
    return (target.base_count * percent + 99) // 100
