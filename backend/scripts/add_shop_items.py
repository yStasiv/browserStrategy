import json
import sys
from argparse import ArgumentParser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import database, models
from backend.services.artifact_shop import BONUS_LABELS
from backend.services.hero_equipment import ITEM_SLOTS
from backend.services.resource_balances import resource_definitions


ARTIFACTS_FILE = Path(__file__).resolve().parents[2] / "content" / "artifacts.json"


def add_shop_items(db: Session, *, sync_existing=False):
    artifacts = json.loads(ARTIFACTS_FILE.read_text(encoding="utf-8"))
    resource_ids = resource_definitions().keys() - {"gold"}
    for item in artifacts:
        if item["item_type"] not in ITEM_SLOTS:
            raise ValueError(f"Невідомий тип артефакту: {item['name']}.")
        if item["stats"].keys() - BONUS_LABELS.keys():
            raise ValueError(f"Артефакт «{item['name']}» має непідтримувані характеристики.")
        shop = item["shop_data"]
        if type(shop["price"]) is not int or shop["price"] < 0 or any(
            key not in resource_ids or type(cost) is not int or cost <= 0
            for key, cost in shop.get("resources", {}).items()
        ):
            raise ValueError(f"Некоректна ціна артефакту «{item['name']}».")

    existing = {}
    if sync_existing:
        listings = db.scalars(select(models.ShopItem).join(models.ShopItem.item_template)
                             .where(models.Item.owner_id.is_(None))).all()
        for listing in listings:
            existing.setdefault(listing.item_template.name, []).append(listing)
    for artifact in artifacts:
        item_data = {key: value for key, value in artifact.items() if key not in ("shop_data", "repair_cost")}
        shop = artifact["shop_data"]
        item_data["level_required"] = shop["level"]
        if previous := existing.get(artifact["name"]):
            for listing in previous:
                for key, value in item_data.items():
                    setattr(listing.item_template, key, value)
                listing.price = shop["price"]
                listing.resource_costs = shop.get("resources", {})
                listing.level_required = shop["level"]
            continue
        db.add(models.ShopItem(
            item_template=models.Item(**item_data),
            price=shop["price"],
            resource_costs=shop.get("resources", {}),
            level_required=shop["level"],
            quantity=shop.get("quantity", -1),
        ))
    db.commit()


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--sync-existing", action="store_true")
    args = parser.parse_args()
    with database.SessionLocal() as db:
        add_shop_items(db, sync_existing=args.sync_existing)
    print("Предмети успішно додано до магазину!")
