from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.config import SYSTEM_PLAYER_ID
from backend.models import RewardTransaction, User


def issue_system_resources(
    db: Session, recipient_id: int, source: str, source_key: str, *,
    gold: int, wood: int, stone: int, experience: int = 0,
):
    """Record and credit a validated reward in the caller's transaction."""
    db.add(RewardTransaction(
        issuer_id=SYSTEM_PLAYER_ID, recipient_id=recipient_id, source=source,
        source_key=source_key, gold=gold, wood=wood, stone=stone,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.flush()
    balances = {"gold": User.gold + gold, "wood": User.wood + wood, "stone": User.stone + stone}
    if experience:
        balances["experience"] = User.experience + experience
    db.execute(update(User).where(User.id == recipient_id).values(**balances))
