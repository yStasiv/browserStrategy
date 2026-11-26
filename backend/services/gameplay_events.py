"""Record economy activity in the transaction that changes the player's balance."""
from datetime import UTC, datetime

from backend.models import GameplayEvent


def record(db, kind, *, occurred_at=None, **payload):
    db.add(GameplayEvent(
        kind=kind, payload=payload,
        occurred_at=occurred_at if occurred_at is not None else datetime.now(UTC).replace(tzinfo=None),
    ))
