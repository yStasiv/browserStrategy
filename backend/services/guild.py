import logging
import random
from datetime import datetime, time, timedelta, timezone
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.guild_models import (
    GuildDailyReplacement, GuildEvent, GuildProgress, GuildQuest, GuildQuestSlot,
    GuildQuestTemplate,
)
from backend.services.guild_content import load_templates
from backend.services.guild_experience import xp_threshold
from backend.services.rewards import issue_system_resources

logger = logging.getLogger(__name__)

SLOT_COUNT = 5
DAILY_LIMIT = 3
OBJECTIVE_GROWTH_PERCENT = 20
RANKS = ((10, "Ветеран"), (5, "Шукач пригод"), (1, "Новачок"))
RESOURCE_NAMES = {"singing_resin": "співочої смоли", "basalt_bone": "базальтової кістки"}


class Category(str, Enum):
    COLLECTION = "collection"
    DELIVERY = "delivery"
    ENEMY_DEFEAT = "enemy_defeat"
    HUNTING = "hunting"
    SPECIAL = "special"


class GuildError(Exception):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def utc_today():
    return datetime.now(timezone.utc).date()


def insert_once(db, model, **values):
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    return db.execute(insert(model).values(**values).on_conflict_do_nothing()).rowcount == 1


def lock_progress(db, player_id):
    # The write serializes mutations on SQLite and locks the player row on PostgreSQL.
    result = db.execute(
        update(GuildProgress).where(GuildProgress.player_id == player_id)
        .values(xp=GuildProgress.xp)
    )
    if result.rowcount:
        return db.get(GuildProgress, player_id)
    return None


def quest_catalog(db):
    try:
        templates = load_templates()
    except (OSError, ValueError) as exc:
        logger.error("Invalid guild quest content: %s", exc)
        raise GuildError("Шаблони квестів тимчасово недоступні.", 503) from exc
    # Keep registered keys for historical quest references, including removed templates.
    registered = set(db.scalars(select(GuildQuestTemplate.key)).all())
    new_templates = [template for template in templates if template.key not in registered]
    for template in sorted(new_templates, key=lambda entry: entry.key):
        insert_once(db, GuildQuestTemplate, **template.model_dump())
    return templates


def generate(db, progress, templates, excluded_key=None, preferred_exclusions=()):
    eligible = [
        template for template in templates
        if template.enabled and template.min_level <= progress.level
        and template.category == Category.COLLECTION.value and template.key != excluded_key
    ]
    if not eligible:
        raise GuildError("Немає доступного шаблону квесту.", 503)
    distinct = [template for template in eligible if template.key not in preferred_exclusions]
    template = random.choice(distinct or eligible)
    scale = 100 + (progress.level - 1) * OBJECTIVE_GROWTH_PERCENT
    required = (template.required * scale + 99) // 100
    quest = GuildQuest(
        player_id=progress.player_id, template_key=template.key, generation_level=progress.level,
        title=template.title, description=f"Придбайте {required} од. {RESOURCE_NAMES[template.resource]} на підприємствах.",
        category=template.category, resource=template.resource, difficulty=template.difficulty,
        required=required, progress=0, status="available", gold=template.gold * scale // 100,
        wood=template.wood * scale // 100, stone=template.stone * scale // 100,
        xp=template.xp * scale // 100,
    )
    db.add(quest)
    db.flush()
    return quest


def initialize(db, player_id):
    created = insert_once(
        db, GuildProgress, player_id=player_id, level=1, xp=0, next_xp=xp_threshold(1), claimed_count=0
    )
    if created:
        templates = quest_catalog(db)
        progress = db.get(GuildProgress, player_id)
        keys = set()
        for number in range(1, SLOT_COUNT + 1):
            quest = generate(db, progress, templates, preferred_exclusions=keys)
            keys.add(quest.template_key)
            db.add(GuildQuestSlot(player_id=player_id, number=number, quest_id=quest.id))


def current_quests(db, player_id):
    return db.execute(
        select(GuildQuestSlot, GuildQuest).join(GuildQuest, GuildQuest.id == GuildQuestSlot.quest_id)
        .where(GuildQuestSlot.player_id == player_id).order_by(GuildQuestSlot.number)
    ).all()


def current_quest(db, player_id, quest_id):
    progress = lock_progress(db, player_id)
    if progress is None:
        raise GuildError("Дошку гільдії ще не створено.", 404)
    quests = current_quests(db, player_id)
    for slot, quest in quests:
        if quest.id == quest_id:
            keys = {other.template_key for _, other in quests}
            return progress, slot, quest, keys
    if db.scalar(select(GuildQuest.id).where(GuildQuest.id == quest_id, GuildQuest.player_id == player_id)):
        raise GuildError("Цей квест уже залишив дошку.")
    raise GuildError("Квест не знайдено.", 404)


def claim(db, player_id, quest_id):
    progress, slot, quest, keys = current_quest(db, player_id, quest_id)
    if quest.status != "completed" or quest.progress < quest.required:
        raise GuildError("Спочатку виконайте квест.")
    issue_system_resources(
        db, player_id, "guild_quest", str(quest.id),
        gold=quest.gold, wood=quest.wood, stone=quest.stone,
    )
    progress.xp += quest.xp
    progress.next_xp = xp_threshold(progress.level)
    while quest.xp > 0 and progress.xp >= progress.next_xp:
        progress.xp -= progress.next_xp
        progress.level += 1
        progress.next_xp = xp_threshold(progress.level)
    progress.claimed_count += 1
    quest.status = "reward_claimed"
    slot.quest_id = generate(db, progress, quest_catalog(db), preferred_exclusions=keys).id


def replace(db, player_id, quest_id, confirmed):
    progress, slot, quest, keys = current_quest(db, player_id, quest_id)
    if quest.status not in {"available", "in_progress"}:
        raise GuildError("Завершений квест очікує на отримання нагороди.")
    if quest.progress and not confirmed:
        raise GuildError("Підтвердьте втрату прогресу.")
    today = utc_today()
    insert_once(db, GuildDailyReplacement, player_id=player_id, utc_date=today, used=0)
    result = db.execute(
        update(GuildDailyReplacement).where(
            GuildDailyReplacement.player_id == player_id,
            GuildDailyReplacement.utc_date == today,
            GuildDailyReplacement.used < DAILY_LIMIT,
        ).values(used=GuildDailyReplacement.used + 1)
    )
    if result.rowcount != 1:
        raise GuildError("Денні заміни вичерпано.")
    quest.status = "replaced"
    slot.quest_id = generate(
        db, progress, quest_catalog(db), excluded_key=quest.template_key, preferred_exclusions=keys
    ).id


def record_collection(db, player_id, source_id, resource, amount):
    if resource not in RESOURCE_NAMES or amount <= 0:
        return
    # Record the purchase even when the player has no board yet.
    if not insert_once(
        db, GuildEvent, player_id=player_id, event_type="resource_collected", source_id=source_id
    ):
        return
    if lock_progress(db, player_id) is None:
        return
    for _, quest in current_quests(db, player_id):
        if quest.category == Category.COLLECTION.value and quest.resource == resource and quest.status in {
            "available", "in_progress"
        }:
            quest.progress = min(quest.required, quest.progress + amount)
            quest.status = "completed" if quest.progress == quest.required else "in_progress"


def board(db, player_id):
    progress = db.get(GuildProgress, player_id)
    if progress is None:
        return {"initialized": False}
    today = utc_today()
    usage = db.get(GuildDailyReplacement, (player_id, today))
    reset = datetime.combine(today + timedelta(days=1), time.min, timezone.utc)
    return {
        "initialized": True,
        "level": progress.level,
        "rank": next(rank for level, rank in RANKS if progress.level >= level),
        "xp": progress.xp,
        "next_xp": xp_threshold(progress.level),
        "claimed_count": progress.claimed_count,
        "replacements_remaining": DAILY_LIMIT - (usage.used if usage else 0),
        "replacement_limit": DAILY_LIMIT,
        "replacement_reset_at": reset.isoformat(),
        "quests": [
            {
                "id": quest.id, "slot": slot.number, "title": quest.title,
                "description": quest.description.replace("деревини", "співочої смоли").replace("каменю", "базальтової кістки"), "category": quest.category,
                "difficulty": quest.difficulty, "required": quest.required, "progress": quest.progress,
                "status": quest.status, "gold": quest.gold, "singing_resin": quest.wood, "basalt_bone": quest.stone,
                "xp": quest.xp,
            }
            for slot, quest in current_quests(db, player_id)
        ],
    }
