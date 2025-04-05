from sqlalchemy.orm import Session

from backend import database, models


def add_shop_items(db: Session):
    # Спочатку створимо базові предмети (шаблони)
    base_items = [
        # Одноручна зброя (one_handed_weapon)
        {
            "name": "Меч Лицаря",
            "description": "Класичний одноручний меч, збалансований для бою. Лезо сталеве з легким вигином, руків'я обмотане чорною шкірою, хрестовина пряма, а на наверші гербовий знак.",
            "item_type": "one_handed_weapon",
            "image_url": "/static/images/items/knight_sword.png",
            "rarity": "common",
            "set": None,
            "stats": {
                "melee_attack": 5,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 0,
                "magic_resistance": 0,
                "initiative": 0,
                "stamina": 0,
            },
            "shop_data": {"price": 200, "level": 3},
            "durability": 20,
            "max_durability": 20,
        },
        {
            "name": "Клинок Вбивці",
            "description": "Ллегкий та елегантний меч із загостреним кінцем. Лезо тонке, темного металу, руків'я загорнуте в червону тканину, а хрестовина вигнута, що додає стилю. Виглядає створеним для швидких і точних ударів.",
            "item_type": "one_handed_weapon",
            "image_url": "/static/images/items/assassin_blade.png",
            "rarity": "rare",
            "set": "assassin_gear",
            "stats": {
                "melee_attack": 4,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 0,
                "magic_resistance": 0,
                "initiative": 2,
                "chance_crit": 5,
            },
            "shop_data": {"price": 350, "level": 6},
            "durability": 18,
            "max_durability": 18,
        },
        # Дворучна зброя (two_handed_weapon)
        {
            "name": "Молот Титана",
            "description": "В величезний дворукий бойовий молот. Головка з масивного темного металу, інкрустована магічними символами. Рукоятка обгорнута шкірою для кращого зчеплення. Випромінює силу та здатен оглушувати ворогів.",
            "item_type": "two_handed_weapon",
            "image_url": "/static/images/items/titan_hammer.png",
            "rarity": "legendary",
            "set": None,
            "stats": {
                "melee_attack": 12,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 0,
                "magic_resistance": 0,
                "initiative": -2,
                "stamina": 5,
                "chance_stun": 10,
            },
            "shop_data": {"price": 800, "level": 10},
            "durability": 25,
            "max_durability": 25,
        },
        # Обладунки (armor)
        {
            "name": "Обладунок Льоду",
            "description": "Крижаний панцир, що захищає від вогню.",
            "item_type": "armor",
            "image_url": "/static/images/items/ice_armor.svg",
            "rarity": "epic",
            "set": "frost_guard",
            "stats": {
                "melee_attack": 0,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 10,
                "magic_resistance": 5,
                "fire_resistance": 15,
                "stamina": 3,
            },
            "shop_data": {"price": 700, "level": 8},
            "durability": 30,
            "max_durability": 30,
        },
        {
            "name": "Кольчуга",
            "description": "Середня броня з металевих кілець",
            "item_type": "armor",
            "image_url": "/static/images/items/chainmail.svg",
            "rarity": "epic",
            "set": "frost_guard",
            "stats": {
                "melee_attack": 0,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 1,
                "magic_resistance": 0,
                "fire_resistance": 0,
                "stamina": 3,
            },
            "shop_data": {"price": 100, "level": 1},
            "durability": 12,
            "max_durability": 12,
        },
        # Шоломи
        {
            "name": "Шолом Дракона",
            "description": "Легендарний шолом, що входить у комплект 'Драконяча Лють'.",
            "item_type": "helmet",
            "image_url": "/static/images/items/dragon_helmet.svg",
            "rarity": "epic",
            "set": "dragon_fury",
            "stats": {
                "melee_attack": 0,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 5,
                "magic_resistance": 3,
                "stamina": 2,
            },
            "shop_data": {"price": 500, "level": 7},
            "durability": 22,
            "max_durability": 22,
        },
        # Чоботи (boots)
        {
            "name": "Чоботи Тіней",
            "description": "Легкі чоботи, що допомагають зникати в тінях.",
            "item_type": "boots",
            "image_url": "/static/images/items/shadow_boots.svg",
            "rarity": "rare",
            "set": "assassin_gear",
            "stats": {
                "melee_attack": 0,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 2,
                "magic_resistance": 2,
                "initiative": 4,
                "chance_crit": 3,
            },
            "shop_data": {"price": 400, "level": 6},
            "durability": 18,
            "max_durability": 18,
        },
        # Плащі (back)
        {
            "name": "Плащ Тіней",
            "description": "Частина 'Сету Вбивці', робить власника менш помітним.",
            "item_type": "back",
            "image_url": "/static/images/items/shadow_cloak.svg",
            "rarity": "epic",
            "set": "assassin_gear",
            "stats": {
                "melee_attack": 0,
                "ranged_attack": 0,
                "magic_potential": 0,
                "physical_defense": 3,
                "magic_resistance": 5,
                "dodge_chance": 5,
            },
            "shop_data": {"price": 650, "level": 9},
            "durability": 20,
            "max_durability": 20,
        },
        # Прикраси (jewelry)
        {
            "name": "Амулет Сили",
            "description": "Підвищує фізичну силу носія.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/stamina_amulet.svg",
            "rarity": "common",
            "set": None,
            "stats": {"stamina": 1},
            "shop_data": {"price": 200, "level": 2},
            "durability": 10,
            "max_durability": 10,
        },
        {
            "name": "Кільце Захисту",
            "description": "Збільшує броню власника.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/armor_ring.svg",
            "rarity": "common",
            "set": None,
            "stats": {"armor": 2},
            "shop_data": {"price": 200, "level": 2},
            "durability": 10,
            "max_durability": 10,
        },
        {
            "name": "Перстень Влучності",
            "description": "Підвищує точність у дальньому бою.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/accuracy_ring.svg",
            "rarity": "uncommon",
            "set": "sharpshooter_gear",
            "stats": {"ranged_attack": 2, "initiative": 1},
            "shop_data": {"price": 300, "level": 3},
            "durability": 12,
            "max_durability": 12,
        },
        {
            "name": "Амулет Мудрості",
            "description": "Збільшує магічний потенціал носія.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/wisdom_amulet.svg",
            "rarity": "rare",
            "set": "mage_set",
            "stats": {"magic_potential": 3, "magic_resistance": 1},
            "shop_data": {"price": 500, "level": 5},
            "durability": 15,
            "max_durability": 15,
        },
        {
            "name": "Смарагдовий Оберіг",
            "description": "Захищає від магії природи.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/emerald_amulet.svg",
            "rarity": "epic",
            "set": "nature_guard",
            "stats": {"magic_resistance": 4, "stamina": 2},
            "shop_data": {"price": 700, "level": 7},
            "durability": 20,
            "max_durability": 20,
        },
        {
            "name": "Криваве Кільце",
            "description": "Посилює ближній бій ціною здоров'я.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/blood_ring.svg",
            "rarity": "legendary",
            "set": "berserker_gear",
            "stats": {"melee_attack": 4, "stamina": -1},
            "shop_data": {"price": 900, "level": 9},
            "durability": 25,
            "max_durability": 25,
        },
        {
            "name": "Сапфіровий Амулет",
            "description": "Древній амулет, що підвищує стійкість до магії.",
            "item_type": "jewelry",
            "image_url": "/static/images/items/sapphire_amulet.svg",
            "rarity": "epic",
            "set": "arcane_guard",
            "stats": {"magic_resistance": 5, "initiative": 1},
            "shop_data": {"price": 750, "level": 8},
            "durability": 22,
            "max_durability": 22,
        },
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
            max_durability=item_data["max_durability"],
        )
        db.add(item)
        db.flush()  # Щоб отримати id предмета

        # Створюємо товар у магазині
        shop_item = models.ShopItem(
            item_template_id=item.id,
            price=item_data["shop_data"]["price"],
            level_required=item_data["shop_data"]["level"],
            quantity=-1,  # Необмежена кількість
        )
        db.add(shop_item)

    # Додаємо кілька предметів з обмеженою кількістю
    limited_items = [
        {
            "name": "Легендарний меч",
            "description": "Рідкісний могутній меч",
            "item_type": "one_handed_weapon",
            "image_url": "/static/images/items/legendary_sword.svg",
            "stats": {
                "damage": 10,
            },
            "shop_data": {"price": 1000, "level": 10, "quantity": 5},
        }
    ]

    for item_data in limited_items:
        item = models.Item(
            name=item_data["name"],
            description=item_data["description"],
            item_type=item_data["item_type"],
            image_url=item_data["image_url"],
            stats=item_data["stats"],
        )
        db.add(item)
        db.flush()

        shop_item = models.ShopItem(
            item_template_id=item.id,
            price=item_data["shop_data"]["price"],
            level_required=item_data["shop_data"]["level"],
            quantity=item_data["shop_data"]["quantity"],
        )
        db.add(shop_item)

    db.commit()


if __name__ == "__main__":
    db = next(database.get_db())
    add_shop_items(db)
