from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import RewardTransaction, User


def system_player_id(db):
    return db.execute(select(User.id).where(User.is_system.is_(True))).scalar_one()


def issue_system_resources(
    db: Session, recipient_id: int, source: str, source_key: str, *,
    gold: int, wood: int, stone: int, experience: int = 0, reward_entries=None,
):
    """Record and credit a validated reward in the caller's transaction."""
    db.add(RewardTransaction(
        issuer_id=system_player_id(db), recipient_id=recipient_id, source=source,
        source_key=source_key, gold=gold, wood=wood, stone=stone,
        reward_entries=reward_entries,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.flush()
    balances = {"gold": User.gold + gold, "singing_resin": User.singing_resin + wood, "basalt_bone": User.basalt_bone + stone}
    if experience:
        balances["experience"] = User.experience + experience
    db.execute(update(User).where(User.id == recipient_id).values(**balances))
