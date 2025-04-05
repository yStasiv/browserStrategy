from sqlalchemy.orm import Session

from backend import database, models


def add_test_items(db: Session):
    # Тестові предмети
    test_items = [
        # Шоломи
        {
            "name": "Шолом новачка",
            "description": "Простий шолом для початківців",
            "item_type": "helmet",
            "image_url": "../static/images/items/novice_helmet.png",
            "stats": {"armor": 2},
        },
        # Броня
        {
            "name": "Шкіряна броня",
            "description": "Базова броня з шкіри",
            "item_type": "armor",
            "image_url": "../static/images/items/leather_armor.png",
            "stats": {"armor": 5},
        },
        # Зброя
        {
            "name": "Короткий меч",
            "description": "Одноручний меч",
            "item_type": "one_handed_weapon",
            "image_url": "../static/images/items/short_sword.png",
            "stats": {"damage": 5},
        },
        {
            "name": "Дворучний меч",
            "description": "Важкий дворучний меч",
            "item_type": "two_handed_weapon",
            "image_url": "../static/images/items/two_handed_sword.png",
            "stats": {"damage": 12},
        },
        # Взуття
        {
            "name": "Шкіряні чоботи",
            "description": "Прості чоботи",
            "item_type": "boots",
            "image_url": "../static/images/items/leather_boots.png",
            "stats": {"armor": 2},
        },
        # Прикраси
        {
            "name": "Амулет сили",
            "description": "Підвищує силу носія",
            "item_type": "jewelry",
            "image_url": "../static/images/items/agility_amulet.png",
            "stats": {"agility": 1},
        },
        # Предмети на спину
        {
            "name": "Плащ мандрівника",
            "description": "Теплий плащ",
            "item_type": "back",
            "image_url": "../static/images/items/traveler_cloak.png",
            "stats": {"armor": 1},
        },
    ]

    # Додаємо предмети в базу даних
    for item_data in test_items:
        item = models.Item(
            name=item_data["name"],
            description=item_data["description"],
            item_type=item_data["item_type"],
            image_url=item_data["image_url"],
            stats=item_data["stats"],
        )
        db.add(item)

    db.commit()


if __name__ == "__main__":
    db = next(database.get_db())
    add_test_items(db)
