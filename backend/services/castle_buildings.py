import json
from pathlib import Path
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter
from sqlalchemy import select

from backend.models import CastleBuilding, PlayerResourceBalance
from backend.services.character_profile import LEGACY_BALANCES, RESOURCE_FILE


CATALOG_FILE = Path(__file__).resolve().parents[2] / "content" / "castle_buildings.json"
FORGE = "forge"
MAGIC_SCHOOL = "magic_school_1"
Cost = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]


class Building(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    name: str = Field(min_length=1)
    description: str = ""
    factions: list[str] = Field(default_factory=list)
    min_level: int = Field(strict=True, ge=1)
    resources: dict[str, Cost] = Field(default_factory=dict)
    built_by_default: bool = False


def catalog():
    buildings = TypeAdapter(list[Building]).validate_json(CATALOG_FILE.read_text(encoding="utf-8"))
    entries = {building.id: building for building in buildings}
    resources = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
    names = {row["id"]: row["name"] for row in (*resources["permanent"], resources["unique"])}
    if len(entries) != len(buildings):
        raise ValueError("Ідентифікатори будівель мають бути унікальними.")
    for building in buildings:
        unknown = building.resources.keys() - names.keys()
        if unknown:
            raise ValueError(f"Невідомі ресурси для {building.id}: {', '.join(sorted(unknown))}")
    return entries, names


def built_ids(db, player, entries):
    purchased = db.scalars(select(CastleBuilding.building_id).where(CastleBuilding.player_id == player.id))
    return set(purchased) | {
        building.id for building in entries.values()
        if building.built_by_default and available_to_faction(building, player)
    }


def available_to_faction(building, player):
    return not building.factions or (player.fraction or "").casefold() in {
        faction.casefold() for faction in building.factions
    }


def build(db, player, building_id):
    # The route holds the player lock obtained from require_presence.
    entries, names = catalog()
    building = entries.get(building_id)
    if building is None or not available_to_faction(building, player):
        raise HTTPException(404, "Ця будівля недоступна для твоєї фракції.")
    if building_id in built_ids(db, player, entries):
        raise HTTPException(409, "Цю будівлю вже побудовано.")
    if player.level < building.min_level:
        raise HTTPException(403, f"Потрібен бойовий рівень {building.min_level}.")

    balances = {}
    for resource, cost in building.resources.items():
        if resource in LEGACY_BALANCES:
            owner, field = player, resource
        else:
            owner, field = db.get(PlayerResourceBalance, (player.id, resource)), "quantity"
        balance = (getattr(owner, field) or 0) if owner is not None else 0
        if balance < cost:
            raise HTTPException(409, f"Недостатньо ресурсу «{names[resource]}».")
        balances[resource] = (owner, field, balance - cost)
    for owner, field, remaining in balances.values():
        setattr(owner, field, remaining)
    db.add(CastleBuilding(player_id=player.id, building_id=building_id))
