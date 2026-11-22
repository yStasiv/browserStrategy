import json
from pathlib import Path
from typing import Annotated

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter
from sqlalchemy import select

from backend.config import LEGACY_BALANCES, RESOURCE_FILE
from backend.engine.data import faction_key
from backend.models import CastleBuilding, PlayerResourceBalance


CATALOG_FILE = Path(__file__).resolve().parents[2] / "content" / "castle_buildings.json"
BUILD_ICON_FILE = CATALOG_FILE.parents[1] / "frontend" / "static" / "images" / "buildings" / "build.png"
FORGE = "forge"
MAGIC_SCHOOL = "magic_school_1"
Cost = Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]


class Building(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    name: str = Field(min_length=1)
    description: str = ""
    image_url: str | None = None
    factions: list[str] = Field(default_factory=list)
    min_level: int = Field(strict=True, ge=1)
    resources: dict[str, Cost] = Field(default_factory=dict)
    built_by_default: bool = False
    built_on_registration: bool = False
    requires: list[str] = Field(default_factory=list)


def catalog():
    buildings = TypeAdapter(list[Building]).validate_json(CATALOG_FILE.read_text(encoding="utf-8"))
    entries = {building.id: building for building in buildings}
    resources = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
    resource_catalog = {row["id"]: row for row in (*resources["permanent"], resources["unique"])}
    if len(entries) != len(buildings):
        raise ValueError("Ідентифікатори будівель мають бути унікальними.")
    for building in buildings:
        unknown = building.resources.keys() - resource_catalog.keys()
        if unknown:
            raise ValueError(f"Невідомі ресурси для {building.id}: {', '.join(sorted(unknown))}")
        if set(building.requires) - entries.keys():
            raise ValueError(f"Невідомі вимоги до будівлі {building.id}.")
    return entries, resource_catalog


def built_ids(db, player, entries):
    purchased = db.scalars(select(CastleBuilding.building_id).where(CastleBuilding.player_id == player.id))
    return set(purchased) | {
        building.id for building in entries.values()
        if building.built_by_default and available_to_faction(building, player)
    }


def available_to_faction(building, player):
    return not building.factions or faction_key(player.fraction) in {faction_key(value) for value in building.factions}


def grant_starter_buildings(db, player):
    entries, _ = catalog()
    db.add_all([
        CastleBuilding(player_id=player.id, building_id=building.id)
        for building in entries.values()
        if building.built_on_registration and available_to_faction(building, player)
    ])


def school_level(built):
    return max((level for level in range(1, 8) if f"magic_school_{level}" in built), default=0)


def build(db, player, building_id):
    # The route holds the player lock obtained from require_presence.
    entries, resources = catalog()
    building = entries.get(building_id)
    if building is None or not available_to_faction(building, player):
        raise HTTPException(404, "Ця будівля недоступна для твоєї фракції.")
    built = built_ids(db, player, entries)
    if building_id in built:
        raise HTTPException(409, "Цю будівлю вже побудовано.")
    if player.level < building.min_level:
        raise HTTPException(403, f"Потрібен бойовий рівень {building.min_level}.")
    missing = [entries[key].name for key in building.requires if key not in built]
    if missing:
        raise HTTPException(403, f"Спочатку побудуй: {', '.join(missing)}.")

    balances = {}
    for resource, cost in building.resources.items():
        if resource in LEGACY_BALANCES:
            owner, field = player, resource
        else:
            owner, field = db.get(PlayerResourceBalance, (player.id, resource)), "quantity"
        balance = (getattr(owner, field) or 0) if owner is not None else 0
        if balance < cost:
            raise HTTPException(409, f"Недостатньо ресурсу «{resources[resource]['name']}».")
        balances[resource] = (owner, field, balance - cost)
    for owner, field, remaining in balances.values():
        setattr(owner, field, remaining)
    db.add(CastleBuilding(player_id=player.id, building_id=building_id))
