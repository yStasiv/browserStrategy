"""Read legacy wallet columns and extended resource balances together."""
import json

from sqlalchemy import select

from backend.config import LEGACY_BALANCES, RESOURCE_FILE
from backend.models import PlayerResourceBalance


def resource_definitions():
    data = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
    return {row["id"]: row for row in (*data["permanent"], data["unique"])}


def resource_owners(db, player, resource_ids):
    resource_ids = set(resource_ids)
    owners = {resource: (player, resource) for resource in resource_ids & LEGACY_BALANCES}
    other_ids = resource_ids - LEGACY_BALANCES
    if other_ids:
        rows = db.scalars(select(PlayerResourceBalance).where(
            PlayerResourceBalance.player_id == player.id,
            PlayerResourceBalance.resource_id.in_(other_ids),
        ))
        owners.update((row.resource_id, (row, "quantity")) for row in rows)
    return owners


def resource_quantity(owners, resource):
    owner, field = owners.get(resource, (None, None))
    return (getattr(owner, field) or 0) if owner is not None else 0
