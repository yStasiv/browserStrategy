from backend import models, database
from sqlalchemy.orm import Session

def add_shop_items(db: Session):
    # Спочатку створимо базові предмети (шаблони)
    base_items = [
        # Зброя
        {
            "name": "Іржавий меч",
            "description": "Простий одноручний меч",
            "item_type": "one_handed_weapon",
            "image_url": "/static/images/items/rusty_sword.svg",
            "stats": {"damage": 3},
            "shop_data": {"price": 100, "level": 1},
            "durability": 5,  # Додаємо міцність
            "max_durability": 5
        },
        {
            "name": "Бойовий меч",
            "description": "Якісний одноручний меч",
            "item_type": "one_handed_weapon",
            "image_url": "/static/images/items/battle_sword.svg",
            "stats": {"damage": 5},
            "shop_data": {"price": 250, "level": 3},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        },
        {
            "name": "Дворучний меч",
            "description": "Важкий дворучний меч",
            "item_type": "two_handed_weapon",
            "image_url": "/static/images/items/two_handed_sword.svg",
            "stats": {"damage": 8},
            "shop_data": {"price": 400, "level": 5},
            "durability": 15,  # Додаємо міцність
            "max_durability": 15
        },
        # Броня
        {
            "name": "Шкіряна броня",
            "description": "Легка броня з шкіри",
            "item_type": "armor",
            "image_url": "/static/images/items/leather_armor.svg",
            "stats": {"armor": 4},
            "shop_data": {"price": 150, "level": 1},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        },
        {
            "name": "Кольчуга",
            "description": "Середня броня з металевих кілець",
            "item_type": "armor",
            "image_url": "/static/images/items/chainmail.svg",
            "stats": {"armor": 6},
            "shop_data": {"price": 300, "level": 4},
            "durability": 15,  # Додаємо міцність
            "max_durability": 15
        },
        # Шоломи
        {
            "name": "Шкіряний шолом",
            "description": "Простий шолом зі шкіри",
            "item_type": "helmet",
            "image_url": "/static/images/items/leather_helmet.svg",
            "stats": {"armor": 2},
            "shop_data": {"price": 80, "level": 1},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        },
        # Взуття
        {
            "name": "Шкіряні чоботи",
            "description": "Прості чоботи",
            "item_type": "boots",
            "image_url": "/static/images/items/leather_boots.svg",
            "stats": {"armor": 1, "speed": 1},
            "shop_data": {"price": 70, "level": 1},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        },
        # Прикраси
        {
            "name": "Амулет сили",
            "description": "Підвищує силу носія",
            "item_type": "jewelry",
            "image_url": "/static/images/items/strength_amulet.svg",
            "stats": {"strength": 1},
            "shop_data": {"price": 200, "level": 2},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        },
        {
            "name": "Кільце захисту",
            "description": "Підвищує захист носія",
            "item_type": "jewelry",
            "image_url": "/static/images/items/armor_ring.svg",
            "stats": {"armor": 1},
            "shop_data": {"price": 200, "level": 2},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        },
        # Предмети на спину
        {
            "name": "Плащ мандрівника",
            "description": "Теплий плащ",
            "item_type": "back",
            "image_url": "/static/images/items/traveler_cloak.svg",
            "stats": {"armor": 1, "initiative": 1},
            "shop_data": {"price": 120, "level": 1},
            "durability": 10,  # Додаємо міцність
            "max_durability": 10
        }
    ]

    # Створюємо предмети та додаємо їх у магазин
    for item_data in base_items:
        # Створюємо базовий предмет (шаблон)
        item = models.Item(
            name=item_data["name"],
            description=item_data["description"],
            item_type=item_data["item_type"],
            image_url=item_data["image_url"],
            stats=item_data["stats"],
            durability=item_data["durability"],
            max_durability=item_data["max_durability"]
        )
        db.add(item)
        db.flush()  # Щоб отримати id предмета
        
        # Створюємо товар у магазині
        shop_item = models.ShopItem(
            item_template_id=item.id,
            price=item_data["shop_data"]["price"],
            level_required=item_data["shop_data"]["level"],
            quantity=-1  # Необмежена кількість
        )
        db.add(shop_item)
    
    # Додаємо кілька предметів з обмеженою кількістю
    limited_items = [
        {
            "name": "Легендарний меч",
            "description": "Рідкісний могутній меч",
            "item_type": "one_handed_weapon",
            "image_url": "/static/images/items/legendary_sword.svg",
            "stats": {"damage": 10, "strength": 2},
            "shop_data": {"price": 1000, "level": 10, "quantity": 5}
        }
    ]

    for item_data in limited_items:
        item = models.Item(
            name=item_data["name"],
            description=item_data["description"],
            item_type=item_data["item_type"],
            image_url=item_data["image_url"],
            stats=item_data["stats"]
        )
        db.add(item)
        db.flush()
        
        shop_item = models.ShopItem(
            item_template_id=item.id,
            price=item_data["shop_data"]["price"],
            level_required=item_data["shop_data"]["level"],
            quantity=item_data["shop_data"]["quantity"]
        )
        db.add(shop_item)
    
    db.commit()

if __name__ == "__main__":
    db = next(database.get_db())
    add_shop_items(db) 