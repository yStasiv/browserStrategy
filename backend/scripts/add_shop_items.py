import json
import sys
from argparse import ArgumentParser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend import database, models
from backend.services.artifact_shop import BONUS_LABELS
from backend.services.hero_equipment import ITEM_SLOTS
from backend.services.resource_balances import resource_definitions


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_FILE = PROJECT_ROOT / "content" / "artifacts.json"
STATIC_ITEMS = PROJECT_ROOT / "frontend" / "static" / "images" / "items"


def add_shop_items(db: Session, *, sync_existing=False):
    artifacts = json.loads(ARTIFACTS_FILE.read_text(encoding="utf-8"))
    resource_ids = resource_definitions().keys() - {"gold"}
    for item in artifacts:
        if item["item_type"] not in ITEM_SLOTS:
            raise ValueError(f"Невідомий тип артефакту: {item['name']}.")
        if item["stats"].keys() - BONUS_LABELS.keys():
            raise ValueError(f"Артефакт «{item['name']}» має непідтримувані характеристики.")
        image_url = item["image_url"]
        filename = Path(image_url).name
        category = item["item_type"]
        if (image_url != f"/static/images/items/{category}/{filename}"
                or not (STATIC_ITEMS / category / filename).is_file()):
            raise ValueError(f"Зображення артефакту «{item['name']}» відсутнє в каталозі {category}.")
        if (type(item["durability"]) is not int or type(item["max_durability"]) is not int
                or item["durability"] <= 0 or item["durability"] != item["max_durability"]):
            raise ValueError(f"Некоректна початкова міцність артефакту «{item['name']}».")
        repair_cost = item.get("repair_cost")
        if repair_cost is not None and (not isinstance(repair_cost, dict)
                                        or type(repair_cost.get("gold")) is not int or repair_cost["gold"] <= 0):
            raise ValueError(f"Некоректна ціна ремонту артефакту «{item['name']}».")
        shop = item["shop_data"]
        stock = shop.get("quantity", -1)
        if type(shop["level"]) is not int or shop["level"] < 1 or type(stock) is not int or stock < -1:
            raise ValueError(f"Некоректні рівень або залишок артефакту «{item['name']}».")
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
        item_data = {key: value for key, value in artifact.items() if key not in ("shop_data", "repair_cost", "name_en")}
        shop = artifact["shop_data"]
        item_data["level_required"] = shop["level"]
        item_data["initial_max_durability"] = artifact.get("max_durability")
        if sync_existing:
            db.execute(update(models.Item).where(
                models.Item.owner_id.is_not(None),
                models.Item.name == artifact["name"],
                models.Item.item_type == artifact["item_type"],
            ).values(image_url=artifact["image_url"]))
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
