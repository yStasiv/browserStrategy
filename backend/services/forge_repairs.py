"""Pricing, risk and settlement for one repair job per character."""
import json
import secrets
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update

from backend.engine.data import CONTENT
from backend.models import Item, RepairJob, RewardTransaction
from backend.services import activity_guilds as guilds
from backend.services.hero_equipment import change_equipment, equipment_ids, lock_hero


def repair_prices():
    rows = json.loads((CONTENT / "artifacts.json").read_text(encoding="utf-8"))
    prices = {(row["name"], row["item_type"]): row["repair_cost"]["gold"]
              for row in rows if "repair_cost" in row}
    if any(type(gold) is not int or gold <= 0 for gold in prices.values()):
        raise ValueError("Ціна ремонту в каталозі має бути додатною цілою сумою золота.")
    return prices


def duration_minutes(gold):
    return max(1, (gold + 99) // 100)


def repair_points(gold):
    return (Decimal(gold) / 500).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def success_chance(item, level):
    initial = item.initial_max_durability or item.max_durability
    return min(100, max(0, item.max_durability * 100 // initial + level * 3))


def preview(item, level, gold):
    return {
        "gold": gold, "minutes": duration_minutes(gold), "points": format(repair_points(gold), "f"),
        "chance": success_chance(item, level), "percent": guilds.repair_percent(level),
        "refund": gold // 2,
    }


def start(db, player, item, workshop, level, gold, now, confirmed):
    if db.get(RepairJob, player.id) is not None:
        raise HTTPException(409, "Спочатку забери результат поточного ремонту.")
    plan = preview(item, level, gold)
    if plan["chance"] < 50 and not confirmed:
        raise HTTPException(409, "Підтвердь ризик знищення предмета.")
    if player.gold < gold:
        raise HTTPException(409, "Недостатньо золота для ремонту.")
    if item.id in equipment_ids(player.equipped_items).values():
        change_equipment(db, player, item_id=item.id, remove=True)
    item.initial_max_durability = item.initial_max_durability or item.max_durability
    player.gold -= gold
    db.add(RepairJob(
        player_id=player.id, item_id=item.id, token=uuid4().hex, workshop=workshop,
        ready_at=now + timedelta(minutes=plan["minutes"]), gold=gold,
        restored=max(1, item.max_durability * plan["percent"] // 100),
        succeeded=secrets.randbelow(100) < plan["chance"],
    ))


def repaired_durability(job, item):
    new_max = item.max_durability - 1
    return min(new_max, item.durability + job.restored), new_max


def claim(db, player, token, now):
    lock_hero(db, player)
    job = db.get(RepairJob, player.id)
    if job is None or job.token != token:
        raise HTTPException(409, "Ремонт уже забрано або його не знайдено.")
    if now < job.ready_at:
        raise HTTPException(409, "Ремонт ще триває.")
    item = db.get(Item, job.item_id)
    if item is None or item.owner_id != player.id:
        raise HTTPException(409, "Предмет ремонту недоступний.")
    db.delete(job)
    db.flush([job])
    if job.succeeded:
        item.durability, item.max_durability = repaired_durability(job, item)
    else:
        player.gold += job.gold // 2
        db.execute(update(RewardTransaction).where(RewardTransaction.item_id == item.id).values(item_id=None))
        db.delete(item)

    points = repair_points(job.gold)
    specialization = guilds.workshop_progress(db, player.id)[job.workshop]
    if specialization["next_xp"] is not None:
        guilds.award_point(db, player.id, guilds.workshop_key(job.workshop), points)
    if guilds.progress(db, player.id, guilds.METALWORKERS)["next_xp"] is not None:
        guilds.award_point(db, player.id, guilds.METALWORKERS, points)
    return job.succeeded, job.workshop
