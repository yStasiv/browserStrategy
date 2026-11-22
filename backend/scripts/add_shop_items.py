import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session

from backend import database, models
from backend.services.hero_equipment import ITEM_SLOTS, MODIFIED_STATS


ARTIFACTS_FILE = Path(__file__).resolve().parents[2] / "content" / "artifacts.json"


def add_shop_items(db: Session):
    artifacts = json.loads(ARTIFACTS_FILE.read_text(encoding="utf-8"))
    for item in artifacts:
        if item["item_type"] not in ITEM_SLOTS:
            raise ValueError(f"Невідомий тип артефакту: {item['name']}.")
        if item["stats"].keys() - MODIFIED_STATS:
            raise ValueError(f"Артефакт «{item['name']}» має непідтримувані характеристики.")

    for artifact in artifacts:
        item_data = {key: value for key, value in artifact.items() if key != "shop_data"}
        item = models.Item(**item_data)
        shop = artifact["shop_data"]
        db.add(models.ShopItem(
            item_template=item,
            price=shop["price"],
            level_required=shop["level"],
            quantity=shop.get("quantity", -1),
        ))
    db.commit()


if __name__ == "__main__":
    with database.SessionLocal() as db:
        add_shop_items(db)
    print("Предмети успішно додано до магазину!")
