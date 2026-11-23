"""Read the authoritative outcome and present rewards from the settlement ledger."""
from sqlalchemy import select

from backend.models import Item, RewardTransaction, User

from .battle_models import Battle, BattleParticipant
from .data import UNITS
from .events import SCHEMA_VERSION


REWARD_DISPLAY = {
    "experience": {"label": "Досвід героя", "order": 10},
    "gold": {"label": "Золото", "order": 20, "icon": "/static/images/resources/00_gold.png"},
    "singing_resin": {"label": "Співоча смола", "order": 30, "icon": "/static/images/resources/01_singing_resin.png"},
    "basalt_bone": {"label": "Базальтова кістка", "order": 31, "icon": "/static/images/resources/02_basalt_bone.png"},
    "hunters": {"label": "Очки Братства ловців", "order": 40},
    "artifact": {"label": "Артефакт", "order": 50},
}


def _reward_value(reward):
    amount = reward.get("amount")
    return reward.get("value") if amount is None else amount


def _reward_data(entry, artifact, legacy_experience, state, side):
    details = entry.reward_entries
    if details is None:
        details = [{"type": "experience", "amount": legacy_experience(state, side)}]
    entries = [
        {"type": "gold", "amount": entry.gold},
        {"type": "singing_resin", "amount": entry.wood},
        {"type": "basalt_bone", "amount": entry.stone},
        *details,
    ]
    if artifact:
        entries.append({"type": "artifact", "value": artifact.name, "icon": artifact.image_url})
    return [
        {**REWARD_DISPLAY.get(reward.get("type"), {}), **reward}
        for reward in entries if isinstance(reward, dict) and _reward_value(reward) not in (0, None, "")
    ]


def _ai_name(snapshot, side):
    units = dict.fromkeys(
        stack["unit"] for stack in snapshot.get("stacks", {}).values() if stack["owner"] == side
    )
    return ", ".join(UNITS[key].name for key in units if key in UNITS) or "Військо супротивника"


def completion_data(db, battle_id, state, viewer_id, legacy_experience):
    if state.status != "finished":
        return {"result": None, "reward": None}

    battle = db.get(Battle, battle_id)
    ledger = {
        entry.recipient_id: (entry, artifact)
        for entry, artifact in db.execute(
            select(RewardTransaction, Item)
            .outerjoin(Item, RewardTransaction.item_id == Item.id)
            .where(RewardTransaction.source == "battle_v1", RewardTransaction.source_key == str(battle_id))
        )
    }
    sides = {side: [] for side in (0, 1)}
    viewer_reward = None
    for participant, username in db.execute(
        select(BattleParticipant, User.username)
        .outerjoin(User, BattleParticipant.user_id == User.id)
        .where(BattleParticipant.battle_id == battle_id)
        .order_by(BattleParticipant.side, BattleParticipant.id)
    ):
        side = participant.side
        if participant.user_id is None:
            name = _ai_name(battle.initial_state or battle.state, side)
        else:
            name = username or "Учасник"
        rewards = []
        record = ledger.get(participant.user_id)
        if record:
            entry, artifact = record
            rewards = _reward_data(entry, artifact, legacy_experience, state, side)
            if participant.user_id == viewer_id:
                experience = next((_reward_value(reward) for reward in rewards if reward.get("type") == "experience"), 0)
                viewer_reward = {"gold": entry.gold, "experience": experience}
        sides.setdefault(side, []).append({"name": name, "rewards": rewards})

    return {
        "reward": viewer_reward,
        "result": {
            "battle_id": battle_id, "status": "finished", "winner_side": state.winner,
            "replay_available": battle.initial_state is not None and battle.replay_schema_version == SCHEMA_VERSION,
            "sides": [{"side": side, "participants": participants} for side, participants in sides.items()],
        },
    }
