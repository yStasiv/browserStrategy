"""Artifact offers and atomic purchases."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from backend.services.gameplay_events import record
from backend.services.combat_effects import EFFECT_LABELS, artifact_bonus_rows
from backend.models import Item, ShopItem
from backend.services.hero_attributes import PROFILE_STATS
from backend.services.hero_equipment import INVENTORY_LIMIT, lock_hero
from backend.services.resource_balances import resource_owners, resource_quantity

BONUS_LABELS = {column: name for name, column, _ in PROFILE_STATS.values()} | EFFECT_LABELS
SHOP_CATEGORIES = {
    "helmets": ("Шоломи", "items/background_icons/helmet.png", ("helmet",)),
    "armor": ("Броня", "items/background_icons/armor.png", ("armor", "armor:")),
    "belts": ("Пояси", "items/background_icons/belt.png", ("belt",)),
    "boots": ("Чоботи", "items/background_icons/boots.png", ("boots",)),
    "cloaks": ("Плащі", "items/background_icons/cloak.png", ("back",)),
    "shields": ("Щити", "items/background_icons/shield.png", ("shield",)),
    "jewelry": ("Прикраси", "items/background_icons/ring.png", ("jewelry",)),
    "one_handed": ("Одноручна зброя", "items/background_icons/sword.png", ("one_handed_weapon",)),
    "two_handed": ("Дворучна зброя", "items/background_icons/sword.png", ("two_handed_weapon",)),
    "bows": ("Луки", "items/background_icons/bow.png", ("bow",)),
}


def bonuses(stats):
    return artifact_bonus_rows(stats, BONUS_LABELS)


def costs(listing):
    return {"gold": listing.price, **(listing.resource_costs or {})}


def offer_error(listing, player, owners, full):
    if player.level < listing.level_required:
        return f"Потрібен бойовий рівень {listing.level_required}."
    if listing.quantity == 0:
        return "Розпродано."
    if full:
        return "В інвентарі немає вільного місця."
    if any(resource_quantity(owners, key) < amount for key, amount in costs(listing).items()):
        return "Недостатньо ресурсів."
    return None


def inventory_full(db, player):
    return db.scalar(select(func.count()).select_from(Item).where(Item.owner_id == player.id)) >= INVENTORY_LIMIT


def offers(db, player, my_level, category=None):
    query = select(ShopItem).options(joinedload(ShopItem.item_template, innerjoin=True))
    if my_level:
        query = query.where(ShopItem.level_required <= player.level)
    if category:
        query = query.where(ShopItem.item_template.has(Item.item_type.in_(SHOP_CATEGORIES[category][2])))
    listings = db.scalars(query.order_by(ShopItem.level_required, ShopItem.price, ShopItem.id)).all()
    owners = resource_owners(db, player, {key for listing in listings for key in costs(listing)})
    full = inventory_full(db, player)
    return [
        {
            "listing": listing,
            "bonuses": bonuses(listing.item_template.stats),
            "prices": [(key, amount, resource_quantity(owners, key) < amount)
                       for key, amount in costs(listing).items()],
            "error": offer_error(listing, player, owners, full),
        }
        for listing in listings
    ]


def buy(db, player, listing_id):
    lock_hero(db, player)
    listing = db.get(ShopItem, listing_id, with_for_update=True, populate_existing=True)
    if listing is None or listing.item_template is None:
        raise HTTPException(404, "Артефакт у магазині не знайдено.")
    prices = costs(listing)
    owners = resource_owners(db, player, prices)
    error = offer_error(listing, player, owners, inventory_full(db, player))
    if error:
        raise HTTPException(400, error)
    for key, amount in prices.items():
        if amount:
            owner, field = owners[key]
            setattr(owner, field, resource_quantity(owners, key) - amount)
    source = listing.item_template
    db.add(copy_artifact(listing, player.id))
    if listing.quantity > 0:
        listing.quantity -= 1
    record(db, "shop_purchase", name=source.name, item_type=source.item_type,
           level=listing.level_required, costs=prices)


def copy_artifact(listing, owner_id):
    source = listing.item_template
    return Item(
        owner_id=owner_id, name=source.name, description=source.description, item_type=source.item_type,
        image_url=source.image_url, stats={key: value for key, value in (source.stats or {}).items() if key in BONUS_LABELS},
        durability=source.max_durability if source.max_durability is not None else source.durability,
        max_durability=source.max_durability,
        initial_max_durability=source.initial_max_durability or source.max_durability,
        level_required=listing.level_required,
    )
