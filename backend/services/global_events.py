"""Construction lifecycle and auditable contributions using the existing economy."""
import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import func, select

from backend.config import RESOURCE_FILE
from backend.models import (
    ConstructionContribution, Enterprise, EnterpriseDailyReport, EnterpriseEvent, EnterpriseShift,
    EventConstruction, EventReward, GlobalEvent, GlobalEventAudit, Item, News, PlayerResourceBalance,
    ShopItem, User,
)
from backend.services import economy, world
from backend.services.resource_balances import resource_definitions, resource_owners, resource_quantity
from backend.services.rewards import issue_system_resources, system_player_id

EVENT_TYPE = "ENTERPRISE_CONSTRUCTION"
FRAME_TIME = timedelta(hours=72)
BUILD_TIME = timedelta(hours=120)
STATIC = Path(__file__).resolve().parents[2] / "frontend/static"
IMAGE_PREFIX = "/static/images/enterprise_construction/"
STAGE_PREFIX = IMAGE_PREFIX + "stages/"
REWARD_SOURCE = "global_event"
STAGES = {
    "FOUNDATION": "Фундамент",
    "FOUNDATION_WITH_RESOURCES": "Фундамент із ресурсами",
    "FRAME_CONSTRUCTION": "Будівництво каркаса",
    "BUILDING_CONSTRUCTION": "Зведення будівлі",
    "OPERATIONAL": "Підприємство працює",
}
IMAGE_SUFFIXES = ("foundation", "resources", "frame", "unfinished_walls", "complete")


class Project(BaseModel):
    enterprise_type: str
    name: str = Field(default="", max_length=120)
    stage_images: dict[str, str] = Field(default_factory=dict)
    requirements: dict[str, StrictInt]
    salary: int = Field(gt=0, le=economy.MAX_GOLD)
    item_price: int = Field(gt=0, le=economy.MAX_GOLD)
    max_workers: int = Field(gt=0, le=economy.MAX_GOLD)
    max_storage: int = Field(gt=0, le=economy.MAX_GOLD)
    balance: int = Field(ge=0, le=economy.MAX_GOLD)
    area: int = Field(ge=1, le=999)
    adopt_placeholder: bool = False


class Draft(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=30000)
    rules: str = Field(min_length=1, max_length=12000)
    completion: str = Field(min_length=1, max_length=12000)
    reward_description: str = Field(min_length=1, max_length=12000)
    sector: str
    image_url: str = Field(default="", max_length=255)
    projects: list[Project] = Field(min_length=1)
    base_prices: dict[str, StrictInt] = Field(default_factory=dict)


class Grant(BaseModel):
    gold: int = Field(default=0, ge=0, le=economy.MAX_GOLD)
    resources: dict[str, StrictInt] = Field(default_factory=dict)
    items: dict[int, StrictInt] = Field(default_factory=dict)


class RewardPlan(BaseModel):
    multiplier: Decimal = Field(default=0, ge=0, le=1000, max_digits=10, decimal_places=6)
    everyone: Grant = Field(default_factory=Grant)
    ranks: dict[int, Grant] = Field(default_factory=dict)
    individuals: dict[int, Grant] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def catalog():
    return json.loads(RESOURCE_FILE.with_name("enterprise_construction.json").read_text(encoding="utf-8"))


def canonical_stage_url(url):
    if not url.startswith(STAGE_PREFIX):
        return url
    filename = url.removeprefix(STAGE_PREFIX)
    for definition in catalog()["types"].values():
        legacy_prefix = f"enterprise_{definition['asset_number']}_"
        if filename.startswith(legacy_prefix):
            return f"{STAGE_PREFIX}{definition['asset_name']}_{filename.removeprefix(legacy_prefix)}"
    return url


def static_file(url, prefix="/static/images/"):
    if not url.startswith(prefix) or url.startswith("/static/images/news/"):
        return False
    root = STATIC / "images"
    file = STATIC / canonical_stage_url(url).removeprefix("/static/")
    return file.resolve().is_relative_to(root) and file.suffix.lower() in {
        ".png", ".jpg", ".jpeg", ".webp", ".gif",
    } and file.is_file()


def stage_images(resource):
    name = catalog()["types"][resource]["asset_name"]
    return {stage: f"{STAGE_PREFIX}{name}_stage_{i}_{suffix}.png"
            for i, (stage, suffix) in enumerate(zip(STAGES, IMAGE_SUFFIXES), 1)}


def resolved_images(enterprise_type, overrides):
    if overrides.keys() - STAGES.keys():
        raise HTTPException(422, "Невідома стадія підприємства.")
    images = stage_images(enterprise_type)
    images.update({stage: canonical_stage_url(path.strip()) for stage, path in overrides.items() if path.strip()})
    if not all(len(path) <= 255 and static_file(path) for path in images.values()):
        raise HTTPException(422, "Перевір шляхи до зображень усіх стадій підприємства.")
    return images


def event_or_404(db, event_id, *, admin=False):
    event = db.get(GlobalEvent, event_id, populate_existing=True)
    if event is None or (not admin and event.status in ("DRAFT", "CANCELLED")):
        raise HTTPException(404, "Подію не знайдено.")
    return event


def projects(db, event_id):
    return db.scalars(select(EventConstruction).where(EventConstruction.event_id == event_id)
                      .order_by(EventConstruction.id)).all()


def audit(db, event, admin, action, now):
    db.add(GlobalEventAudit(event_id=event.id, administrator_id=admin.id, action=action, created_at=now))


def valid_amounts(amounts, allowed):
    return all(resource in allowed and 0 < amount <= economy.MAX_GOLD for resource, amount in amounts.items())


def save_draft(db, admin, draft, event_id=None):
    world.lock_world(db)
    event = event_or_404(db, event_id, admin=True) if event_id else GlobalEvent(
        event_type=EVENT_TYPE, status="DRAFT", created_at=world.utc_now(), created_by=admin.id,
    )
    if event.status != "DRAFT":
        raise HTTPException(409, "Редагувати можна лише чернетку.")
    if not world.location_available(db, draft.sector, "enterprises"):
        raise HTTPException(422, "Обери відкритий сектор із підприємствами.")
    if draft.image_url and not static_file(draft.image_url):
        raise HTTPException(422, "Зображення події не знайдено.")
    resources = resource_definitions()
    for project in draft.projects:
        if project.enterprise_type not in catalog()["types"]:
            raise HTTPException(422, "Обери тип підприємства з каталогу будівництва.")
        if not project.requirements or not valid_amounts(project.requirements, resources):
            raise HTTPException(422, "Вкажи додатні цілі кількості ресурсів для кожного підприємства.")
        resolved_images(project.enterprise_type, project.stage_images)
    if not valid_amounts(draft.base_prices, resources):
        raise HTTPException(422, "Перевір базові ціни ресурсів.")
    for key, value in draft.model_dump(exclude={"projects", "base_prices"}).items():
        if key != "image_url" and not value.strip():
            raise HTTPException(422, "Заповни інформацію про подію.")
        setattr(event, key, value.strip())
    event.configuration = {"projects": [project.model_dump() for project in draft.projects],
                           "base_prices": draft.base_prices}
    db.add(event)
    db.flush()
    audit(db, event, admin, "EDIT" if event_id else "CREATE", world.utc_now())
    return event


def placeholder_safe(db, site, definition, sector):
    if (site.id != definition.get("placeholder_id") or sector != "Castle" or site.sector != sector
            or site.name != definition["name"] or not site.owner or not site.owner.is_system
            or site.resource_type != "gold" or site.production_type != "mine"
            or site.workers_count or site.resource_stored or site.input_stock or site.last_production_time
            or site.balance != 1000 or site.salary != 30 or site.item_price != 11):
        return False
    if db.scalar(select(User.id).where(User.workplace == f"enterprise_{site.id}").limit(1)) is not None:
        return False
    return not any(db.scalar(select(model.enterprise_id).where(model.enterprise_id == site.id).limit(1)) is not None
                   for model in (EnterpriseShift, EnterpriseEvent, EnterpriseDailyReport, EventConstruction))


def notification_text(event):
    names = [project.get("name", "").strip() or catalog()["types"][project["enterprise_type"]]["name"]
             for project in event.configuration["projects"]]
    return (
        f"{event.description}\n\nПідприємства\n" + "\n".join(f"• {name}" for name in names)
        + f"\n\nУчасть\n{event.rules}\nВнески приймаються на сторінці підприємства у відповідному секторі."
        + f"\n\nБудівництво\nПісля збору матеріалів каркас будується 72 години, будівля — ще 48 годин."
        + f"\n{event.completion}\n\nНагороди\n{event.reward_description}"
    )


def configured_price(db, resource):
    return db.scalar(select(Enterprise.item_price).where(Enterprise.resource_type == resource,
                     Enterprise.item_price > 0).order_by(Enterprise.id).limit(1))


def start(db, event_id, admin):
    world.lock_world(db)
    event = event_or_404(db, event_id, admin=True)
    if event.status in ("ACTIVE", "COMPLETED", "REWARDED"):
        return event
    if event.status != "DRAFT" or not world.location_available(db, event.sector, "enterprises"):
        raise HTTPException(409, "Подію можна запустити лише у відкритому секторі.")
    if not static_file(event.image_url):
        raise HTTPException(422, "Обери або завантаж зображення події.")
    base_prices = {**event.configuration["base_prices"], "gold": 1}
    needed = set()
    selections = []
    adopted_ids = set()
    pending_prices = {}
    for data in event.configuration["projects"]:
        project = Project.model_validate(data)
        key = project.enterprise_type
        definition = catalog()["types"][key]
        if event.sector not in definition.get("sectors", [event.sector]):
            raise HTTPException(409, "Цей тип підприємства недоступний у вибраному секторі.")
        images = resolved_images(key, project.stage_images)
        site = None
        if project.adopt_placeholder:
            placeholder_id = definition.get("placeholder_id")
            site = db.get(Enterprise, placeholder_id) if placeholder_id is not None else None
            if not site or not placeholder_safe(db, site, definition, event.sector):
                raise HTTPException(409, "Придатну порожню заготовку не знайдено. Зніми позначку, щоб створити нову шахту.")
            if site.id in adopted_ids:
                raise HTTPException(409, "Одну заготовку можна використати лише для однієї шахти.")
            adopted_ids.add(site.id)
        needed.update(project.requirements)
        selections.append((project, definition, images, site))
        pending_prices.setdefault(key, project.item_price)
    for resource in sorted(needed - base_prices.keys()):
        price = configured_price(db, resource)
        if not (price or pending_prices.get(resource)):
            raise HTTPException(422, f"Вкажи базову вартість ресурсу {resource}.")
        base_prices[resource] = price or pending_prices[resource]

    from backend.services.enterprises import lock_enterprise

    total_value_limit = sum(amount * economy.MAX_GOLD for project, _, _, _ in selections
                            for amount in project.requirements.values())
    if total_value_limit >= 2**63:
        raise HTTPException(422, "Сумарна кількість ресурсів перевищує ліміт обліку.")

    for project, definition, images, site in selections:
        original = None
        if site is None:
            site = Enterprise(name=project.name.strip() or definition["name"], sector=event.sector, owner_id=system_player_id(db),
                              production_type="mine", resource_stored=0, workers_count=0, balance=0)
            db.add(site)
            db.flush()
        else:
            site = lock_enterprise(db, site.id)
            if not placeholder_safe(db, site, definition, event.sector):
                raise HTTPException(409, "Стан заготовки змінився. Онови сторінку.")
            original = {field: getattr(site, field) for field in
                        ("name", "resource_type", "salary", "item_price", "max_workers", "max_storage", "area")}
            site.name = project.name.strip() or definition["name"]
        for field in ("salary", "item_price", "max_workers", "max_storage", "area"):
            setattr(site, field, getattr(project, field))
        site.resource_type = project.enterprise_type
        db.add(EventConstruction(event_id=event.id, enterprise_id=site.id, enterprise_type=project.enterprise_type,
                                 requirements=project.requirements, collected={}, stage_images=images,
                                 opening_balance=project.balance))
        if original:
            data = {**event.configuration.get("original_sites", {}), str(site.id): original}
            event.configuration = {**event.configuration, "original_sites": data}
    now = world.utc_now()
    event.configuration = {**event.configuration, "price_overrides": event.configuration["base_prices"],
                           "base_prices": base_prices}
    event.status, event.started_by, event.started_at = "ACTIVE", admin.id, now
    db.add(News(event_id=event.id, status="published", title=event.title, text=notification_text(event),
                image_url=event.image_url, created_at=now, published_at=now))
    audit(db, event, admin, "START", now)
    return event


def update_stage_images(db, event_id, enterprise_id, overrides, admin):
    world.lock_world(db)
    event = event_or_404(db, event_id, admin=True)
    build = for_site(db, enterprise_id)
    if not build or build.event_id != event.id:
        raise HTTPException(404, "Шахта не належить цій події.")
    build.stage_images = resolved_images(build.enterprise_type, {**build.stage_images, **overrides})
    audit(db, event, admin, "EDIT_STAGE_IMAGES", world.utc_now())
    return build.stage_images


def cancel(db, event_id, admin):
    world.lock_world(db)
    event = event_or_404(db, event_id, admin=True)
    if event.status == "CANCELLED":
        return
    if event.status not in ("DRAFT", "ACTIVE") or db.scalar(
        select(ConstructionContribution.id).where(ConstructionContribution.event_id == event.id).limit(1)
    ) is not None:
        raise HTTPException(409, "Подію з внесками або завершену подію не можна скасувати.")
    for build in projects(db, event.id):
        site = db.get(Enterprise, build.enterprise_id)
        original = event.configuration.get("original_sites", {}).get(str(site.id))
        build.enterprise_id = None
        db.flush()
        if original:
            for key, value in original.items():
                setattr(site, key, value)
        else:
            db.delete(site)
    event.status = "CANCELLED"
    audit(db, event, admin, "CANCEL", world.utc_now())


def collection_ratio(build):
    return sum((Fraction(build.collected.get(key, 0), amount) for key, amount in build.requirements.items()),
               Fraction()) / len(build.requirements)


def stage(build, now):
    if build.operational_since:
        return "OPERATIONAL"
    if build.construction_started_at is not None:
        return "BUILDING_CONSTRUCTION" if now >= build.frame_completed_at else "FRAME_CONSTRUCTION"
    return "FOUNDATION_WITH_RESOURCES" if collection_ratio(build) >= Fraction(1, 10) else "FOUNDATION"


def for_site(db, enterprise_id):
    return db.scalar(select(EventConstruction).where(EventConstruction.enterprise_id == enterprise_id))


def ensure_operational(db, enterprise_id):
    build = for_site(db, enterprise_id)
    if build and not build.operational_since:
        raise HTTPException(409, "Підприємство ще будується.")


def finish_due(db, now=None):
    now = now or world.utc_now()
    due = select(EventConstruction).where(EventConstruction.operational_since.is_(None),
                                          EventConstruction.construction_completed_at <= now,
                                          EventConstruction.event_id.in_(select(GlobalEvent.id).where(
                                              GlobalEvent.status == "ACTIVE")))
    if db.scalar(due.with_only_columns(EventConstruction.id).limit(1)) is None:
        return
    world.lock_world(db)
    builds = db.scalars(due.order_by(EventConstruction.enterprise_id).execution_options(populate_existing=True)).all()
    affected = set()
    from backend.services.enterprises import lock_enterprise

    for build in builds:
        site = lock_enterprise(db, build.enterprise_id)
        event = event_or_404(db, build.event_id, admin=True)
        balance = build.opening_balance
        if balance is None:
            # Before revision 33 there was exactly one project of each type.
            balance = next(row["balance"] for row in event.configuration["projects"]
                           if row["enterprise_type"] == build.enterprise_type)
        site.balance = balance
        site.last_production_time = build.construction_completed_at
        build.operational_since = build.construction_completed_at
        affected.add(event.id)
    db.flush()
    for event_id in affected:
        event = event_or_404(db, event_id, admin=True)
        all_builds = projects(db, event_id)
        if all(build.operational_since for build in all_builds):
            event.completed_at = max(build.operational_since for build in all_builds)
            event.status = "COMPLETED"


def contribute(db, player, enterprise_id, resource, quantity, operation, *, now=None):
    world.lock_world(db)
    site = db.get(Enterprise, enterprise_id)
    if site is None:
        raise HTTPException(404, "Підприємство не знайдено.")
    world.require_presence(db, player, site.sector, "enterprises")
    build = for_site(db, enterprise_id)
    if build is None:
        raise HTTPException(404, "Будівництво не знайдено.")
    previous = db.scalar(select(ConstructionContribution).where(ConstructionContribution.player_id == player.id,
                                                               ConstructionContribution.operation_id == operation))
    if previous is not None:
        if (previous.enterprise_id, previous.resource_id, previous.quantity) != (enterprise_id, resource, quantity):
            raise HTTPException(409, "Ідентифікатор операції вже використано.")
        return build
    event = event_or_404(db, build.event_id)
    if event.status == "PAUSED":
        raise HTTPException(409, "Подію призупинено.")
    if event.status != "ACTIVE" or build.construction_started_at:
        raise HTTPException(409, "Збір ресурсів уже завершено.")
    if type(quantity) is not int or quantity <= 0 or resource not in build.requirements:
        raise HTTPException(422, "Обери потрібний ресурс і додатну цілу кількість.")
    collected = build.collected.get(resource, 0)
    if quantity > build.requirements[resource] - collected:
        raise HTTPException(409, "Потрібно менше одиниць ресурсу. Прогрес уже оновився.")
    owners = resource_owners(db, player, [resource])
    available = resource_quantity(owners, resource)
    if available < quantity:
        raise HTTPException(409, "Недостатньо ресурсу.")
    owner, field = owners[resource]
    setattr(owner, field, available - quantity)
    build.collected = {**build.collected, resource: collected + quantity}
    now = now or world.utc_now()
    base = event.configuration["base_prices"][resource]
    unit_price = (base if resource == "gold" or resource in event.configuration.get("price_overrides", {})
                  else configured_price(db, resource) or base)
    db.add(ConstructionContribution(event_id=event.id, enterprise_id=site.id, player_id=player.id,
                                   resource_id=resource, quantity=quantity, unit_price=unit_price,
                                   value=quantity * unit_price, created_at=now, operation_id=operation))
    if all(build.collected.get(key, 0) == amount for key, amount in build.requirements.items()):
        build.construction_started_at = now
        build.frame_completed_at = now + FRAME_TIME
        build.construction_completed_at = now + BUILD_TIME
    db.flush()
    return build


def construction_state(db, build, player, now):
    event = db.get(GlobalEvent, build.event_id)
    paused = event.status == "PAUSED" and not build.operational_since
    stage_time = (event.paused_at or now) if paused else now
    current = stage(build, stage_time)
    definitions = resource_definitions()
    owners = resource_owners(db, player, build.requirements)
    contribution = ConstructionContribution
    personal = dict(db.execute(select(contribution.resource_id, func.sum(contribution.quantity)).where(
        contribution.enterprise_id == build.enterprise_id, contribution.player_id == player.id
    ).group_by(contribution.resource_id)).all())
    progress = None if build.construction_started_at is None else min(
        100, max(0, (stage_time - build.construction_started_at) / BUILD_TIME * 100))
    return {
        "stage": current, "paused": paused, "stage_name": "Будівництво призупинено" if paused else STAGES[current], "event_id": event.id, "event_title": event.title,
        "image_url": build.stage_images[current], "collection_progress": float(collection_ratio(build) * 100),
        "construction_progress": progress, "server_time": world.utc_timestamp(now),
        "next_stage_at": timestamp(build.frame_completed_at if current == "FRAME_CONSTRUCTION"
                                   else build.construction_completed_at),
        "completion_at": timestamp(build.construction_completed_at),
        "started_at": timestamp(build.construction_started_at),
        "resources": [{
            "id": key, "name": definitions[key]["name"], "icon": definitions[key]["icon"], "required": amount,
            "collected": build.collected.get(key, 0), "remaining": amount - build.collected.get(key, 0),
            "available": resource_quantity(owners, key), "personal": personal.get(key, 0),
        } for key, amount in build.requirements.items()],
    }


def timestamp(value):
    return world.utc_timestamp(value) if value is not None else None


def rankings(db, event_id, enterprise_id=None, resource=None):
    contribution = ConstructionContribution
    query = select(User.id, User.username, User.level, contribution.resource_id,
                   func.sum(contribution.quantity), func.sum(contribution.value)).join(
                       User, User.id == contribution.player_id).where(contribution.event_id == event_id)
    if enterprise_id is not None:
        query = query.where(contribution.enterprise_id == enterprise_id)
    totals = {}
    for user_id, name, level, key, amount, value in db.execute(
        query.group_by(User.id, User.username, User.level, contribution.resource_id)
    ):
        row = totals.setdefault(user_id, {"player_id": user_id, "name": name, "level": level,
                                          "resources": {}, "value": 0})
        row["resources"][key] = amount
        row["value"] += value
    ordered = sorted(totals.values(), key=lambda row: (
        -row["resources"].get(resource, 0) if resource else 0, -row["value"], row["player_id"]))
    total = sum(row["value"] for row in ordered)
    for rank, row in enumerate(ordered, 1):
        row.update(rank=rank, percent=round(row["value"] / total * 100, 2) if total else 0)
    return ordered


def statistics(db, event_id, *, enterprise_id=None, resource=None):
    rows = rankings(db, event_id, enterprise_id, resource)
    resources = Counter()
    for row in rows:
        resources.update(row["resources"])
    return {"participants": len(rows), "resources": dict(resources),
            "value": sum(row["value"] for row in rows), "ranking": rows}


def reward_preview(db, event, plan):
    if event.status != "COMPLETED":
        raise HTTPException(409, "Нагороди можна сформувати після завершення події.")
    rows = rankings(db, event.id)
    if not set(plan.individuals) <= {row["player_id"] for row in rows} or not set(plan.ranks) <= set(range(1, len(rows) + 1)):
        raise HTTPException(422, "Укажи наявні місця або учасників.")
    grants = [plan.everyone, *plan.ranks.values(), *plan.individuals.values()]
    allowed = resource_definitions().keys() - {"gold"}
    listings = set(db.scalars(select(ShopItem.id)).all())
    if any(not valid_amounts(grant.resources, allowed) or not valid_amounts(grant.items, listings)
           or sum(grant.items.values()) > 500 for grant in grants):
        raise HTTPException(422, "Перевір нагороди. Предмети задаються ID пропозицій магазину.")
    for row in rows:
        gold = int((Decimal(row["value"]) * plan.multiplier).to_integral_value(rounding=ROUND_DOWN))
        resources, items = Counter(), Counter()
        for grant in (plan.everyone, plan.ranks.get(row["rank"]), plan.individuals.get(row["player_id"])):
            if grant:
                gold += grant.gold
                resources.update(grant.resources)
                items.update(grant.items)
        if gold > economy.MAX_GOLD or not valid_amounts(resources, allowed) or sum(items.values()) > 500:
            raise HTTPException(422, "Нагорода перевищує допустиму кількість.")
        row["reward"] = {"gold": gold, "resources": dict(resources), "items": dict(items)}
    totals = {"gold": sum(row["reward"]["gold"] for row in rows), "resources": Counter(), "items": Counter()}
    for row in rows:
        totals["resources"].update(row["reward"]["resources"])
        totals["items"].update(row["reward"]["items"])
    return {"multiplier": str(plan.multiplier), "participants": rows, "totals": totals}


def queue_rewards(db, event, plan, admin):
    if db.scalar(select(EventReward.id).where(EventReward.event_id == event.id).limit(1)) is not None:
        raise HTTPException(409, "План уже зафіксовано. Скористайся повтором невдалих операцій.")
    preview = reward_preview(db, event, plan)
    now = world.utc_now()
    for row in preview["participants"]:
        db.add(EventReward(event_id=event.id, player_id=row["player_id"], operation_id=str(uuid4()),
                           payload=row["reward"], multiplier=str(plan.multiplier), administrator_id=admin.id,
                           status="PENDING", created_at=now))
    audit(db, event, admin, "CONFIRM_REWARDS", now)


def credit_reward(db, event, reward, admin):
    from backend.services.artifact_shop import copy_artifact, inventory_full
    from backend.services.hero_equipment import lock_hero

    player = db.get(User, reward.player_id)
    lock_hero(db, player)
    payload = reward.payload
    resources = payload["resources"]
    if player.gold + payload["gold"] > economy.MAX_GOLD:
        raise HTTPException(409, "Нагорода перевищує ліміт золота.")
    names = resource_definitions()
    details = [f"Золото: {payload['gold']}"] if payload["gold"] else []
    for resource, amount in resources.items():
        if resource in ("singing_resin", "basalt_bone"):
            current = getattr(player, resource)
        else:
            balance = db.get(PlayerResourceBalance, (player.id, resource))
            current = balance.quantity if balance else 0
        if current + amount > economy.MAX_GOLD:
            raise HTTPException(409, "Нагорода перевищує ліміт ресурсів.")
        if resource not in ("singing_resin", "basalt_bone"):
            if balance is None:
                db.add(PlayerResourceBalance(player_id=player.id, resource_id=resource, quantity=amount))
            else:
                balance.quantity += amount
        details.append(f"{names[resource]['name']}: {amount}")
    for listing_id, amount in payload["items"].items():
        listing = db.get(ShopItem, int(listing_id))
        if listing is None or listing.item_template is None:
            raise HTTPException(409, "Предмет нагороди більше не доступний.")
        for _ in range(amount):
            db.flush()
            if inventory_full(db, player):
                raise HTTPException(409, "У рюкзаку гравця бракує місця.")
            db.add(copy_artifact(listing, player.id))
        details.append(f"{listing.item_template.name}: {amount}")
    now = world.utc_now()
    if details:
        issue_system_resources(db, player.id, REWARD_SOURCE, reward.operation_id, gold=payload["gold"],
                               wood=resources.get("singing_resin", 0), stone=resources.get("basalt_bone", 0),
                               reward_entries=[{"type": key, "amount": value} for key, value in resources.items()])
        db.add(News(event_id=event.id, recipient_id=player.id, title=f"Нагорода · {event.title}",
                    text="\n".join(details), status="published", published_at=now, created_at=now))
    reward.status, reward.issued_at, reward.issued_by, reward.error = "ISSUED", now, admin.id, None
