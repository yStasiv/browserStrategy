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
    unit_evolution_tier: int | None = Field(default=None, strict=True, ge=1, le=3)
    legacy_id: str | None = None


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
        if building.unit_evolution_tier in (2, 3) and not any(
            entries[key].unit_evolution_tier == building.unit_evolution_tier - 1
            for key in building.requires
        ):
            raise ValueError(f"Для {building.id} потрібна споруда попередньої форми.")
    return entries, resource_catalog


def built_ids(db, player, entries):
    purchased = set(db.scalars(select(CastleBuilding.building_id).where(CastleBuilding.player_id == player.id)))
    return purchased | {
        building.id for building in entries.values()
        if (building.built_by_default or building.legacy_id in purchased)
        and available_to_faction(building, player)
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


def unaffordable_buildings(db, player, buildings):
    owners = resource_owners(db, player, {resource for building in buildings for resource in building.resources})
    return {
        building.id for building in buildings
        if any(resource_quantity(owners, resource) < cost for resource, cost in building.resources.items())
    }


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

    owners = resource_owners(db, player, building.resources)
    for resource, cost in building.resources.items():
        if resource_quantity(owners, resource) < cost:
            raise HTTPException(409, f"Недостатньо ресурсу «{resources[resource]['name']}».")
    for resource, cost in building.resources.items():
        owner, field = owners[resource]
        setattr(owner, field, resource_quantity(owners, resource) - cost)
    db.add(CastleBuilding(player_id=player.id, building_id=building_id))
