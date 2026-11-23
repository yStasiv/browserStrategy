"""Server-side employment, production and trading for enterprises."""
import json
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update

from backend.config import ENTERPRISE_SHIFT_DURATION as SHIFT_DURATION
from backend.config import LEGACY_BALANCES, RESOURCE_FILE, SYSTEM_PLAYER_ID
from backend.engine.battle_models import Battle, BattleParticipant
from backend.models import Enterprise, EnterpriseDailyReport, EnterpriseEvent, EnterpriseShift, PlayerResourceBalance, User
from backend.services import economy
from backend.services.activity_guilds import WORKERS, award_point
from backend.services.guild import record_collection
from backend.services.world import utc_now

RULES_FILE = RESOURCE_FILE.with_name("enterprise_rules.json")
KYIV = ZoneInfo("Europe/Kyiv")


class ProductionRules(BaseModel):
    units_per_worker: int | None = Field(default=None, ge=0)
    inputs_per_unit: dict[str, int] = Field(default_factory=dict)
    image_url: str | None = None


class EmploymentRules(BaseModel):
    multiplier_percent: int = Field(default=100, ge=0, le=1000)
    penalty_percent: int = Field(default=0, ge=0, le=100)
    require_victory_between_shifts: bool = False


class PricingRules(BaseModel):
    minimum_percent: int = Field(default=90, gt=0, le=100)
    maximum_percent: int = Field(default=120, ge=100, le=1000)


class Rules(BaseModel):
    pricing: PricingRules
    employment: EmploymentRules
    enterprises: dict[int, ProductionRules]


@lru_cache(maxsize=1)
def resource_names():
    data = json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))
    return {row["id"]: row["name"] for row in (*data["permanent"], data["unique"])}


@lru_cache(maxsize=1)
def rules():
    result = Rules.model_validate_json(RULES_FILE.read_text(encoding="utf-8"))
    for production in result.enterprises.values():
        if any(key == "gold" or key not in resource_names() or amount <= 0
               for key, amount in production.inputs_per_unit.items()):
            raise ValueError("Некоректні виробничі матеріали в enterprise_rules.json")
    return result


def production_rules(site):
    return rules().enterprises.get(site.id, ProductionRules())


def image_url(site):
    return production_rules(site).image_url or (
        "/static/images/sawmill_model.png" if site.resource_type == "singing_resin" else None
    )


def price(site):
    policy = rules().pricing
    return economy.supply_price(max(0, site.item_price), site.resource_stored, site.max_storage,
                                policy.minimum_percent, policy.maximum_percent)


def quote(site, amount):
    unit_price = price(site)
    subtotal = unit_price * amount
    fee = economy.gold_commission(subtotal)
    return {"unit_price": unit_price, "subtotal": subtotal, "fee": fee, "total": subtotal + fee}


def wage(site):
    policy = rules().employment
    base = max(0, site.salary)
    payable = base * policy.multiplier_percent * (100 - policy.penalty_percent) // 10_000
    share = company_wage(base, policy.multiplier_percent, policy.penalty_percent)
    return dict(base_wage=base, multiplier_percent=policy.multiplier_percent,
                penalty_percent=policy.penalty_percent, payable=payable, enterprise_payable=share)


def company_wage(base, multiplier, penalty):
    return base * min(multiplier, 100) * (100 - penalty) // 10_000


def active_shift(db, worker_id):
    return db.scalar(select(EnterpriseShift).where(
        EnterpriseShift.worker_id == worker_id, EnterpriseShift.status == "active",
    ))


def employment_error(db, site, worker):
    if worker.workplace or active_shift(db, worker.id):
        return "Ти вже працюєш на підприємстві."
    if site.workers_count >= site.max_workers:
        return "Вільних робочих місць немає."
    pay = wage(site)
    if pay["payable"] > economy.MAX_GOLD or site.balance < pay["enterprise_payable"]:
        return "На рахунку підприємства бракує золота для зарплати."
    if rules().employment.require_victory_between_shifts:
        last = db.scalar(select(EnterpriseShift.completes_at).where(
            EnterpriseShift.worker_id == worker.id, EnterpriseShift.status == "completed",
        ).order_by(EnterpriseShift.completes_at.desc()).limit(1))
        if last is not None and db.scalar(select(Battle.id).join(BattleParticipant).where(
            BattleParticipant.user_id == worker.id, BattleParticipant.side == Battle.winner_side,
            Battle.status == "finished", Battle.finished_at >= last,
        ).limit(1)) is None:
            return "Перед наступною зміною потрібно перемогти в бою."
    return None


def lock_enterprise(db, enterprise_id):
    # A no-op write locks the row on PostgreSQL and serializes writers on SQLite.
    found = db.execute(update(Enterprise).where(Enterprise.id == enterprise_id)
                       .values(balance=Enterprise.balance).execution_options(synchronize_session=False))
    if found.rowcount != 1:
        raise HTTPException(404, "Підприємство не знайдено.")
    return db.get(Enterprise, enterprise_id, populate_existing=True)


def journal(db, site, kind, now, details, actor_id=None, request_key=None):
    db.add(EnterpriseEvent(enterprise_id=site.id, actor_id=actor_id, kind=kind,
                          created_at=now, details=details, request_key=request_key))


def reporting_day(now):
    return now.replace(tzinfo=timezone.utc).astimezone(KYIV).date()


def daily_hires(db, site_id, days):
    if not days:
        return {}
    start = datetime.combine(min(days), time.min, KYIV).astimezone(timezone.utc).replace(tzinfo=None)
    end = datetime.combine(max(days) + timedelta(days=1), time.min, KYIV).astimezone(timezone.utc).replace(tzinfo=None)
    counts = {day: Counter() for day in days}
    shifts = db.execute(select(EnterpriseShift.started_at, EnterpriseShift.worker_id, User.username)
                        .outerjoin(User, User.id == EnterpriseShift.worker_id)
                        .where(EnterpriseShift.enterprise_id == site_id,
                               EnterpriseShift.started_at >= start, EnterpriseShift.started_at < end))
    for started, worker_id, username in shifts:
        day = reporting_day(started)
        if day in counts:
            counts[day][(worker_id, username)] += 1
    return {
        day: sorted(
            ((username or f"Гравець {worker_id}", worker_id if username else None, count)
             for (worker_id, username), count in hires.items()),
            key=lambda entry: entry[0].casefold(),
        )
        for day, hires in counts.items()
    }


def record_daily(db, site, now, *, produced=0, sold=0, sale_gold=0, wages=0):
    # All callers hold the enterprise row lock.
    key = (site.id, reporting_day(now))
    report = db.get(EnterpriseDailyReport, key)
    if report is None:
        report = EnterpriseDailyReport(enterprise_id=key[0], day=key[1], produced={}, sold={}, sale_gold=0, wages=0)
        db.add(report)
        db.flush([report])
    resource = site.resource_type
    if produced:
        report.produced = {**report.produced, resource: report.produced.get(resource, 0) + produced}
    if sold:
        report.sold = {**report.sold, resource: report.sold.get(resource, 0) + sold}
    report.sale_gold += sale_gold
    report.wages += wages


def start_shift(db, site, worker, now, request_key=None):
    error = employment_error(db, site, worker)
    if error:
        raise HTTPException(400, error)
    pay = wage(site)
    db.add(EnterpriseShift(enterprise_id=site.id, worker_id=worker.id, status="active",
                          started_at=now, completes_at=now + SHIFT_DURATION, **pay))
    site.balance -= pay["enterprise_payable"]
    site.workers_count += 1
    worker.workplace = f"enterprise_{site.id}"
    worker.work_start_time = now
    record_daily(db, site, now)
    award_point(db, worker.id, WORKERS)
    if request_key is not None:
        journal(db, site, "employment", now, {}, worker.id, request_key)


def worker_rate(site):
    configured = production_rules(site).units_per_worker
    rate = configured if configured is not None else (1 if site.production_type == "mine" else site.area)
    return max(0, rate) * (100 + site.workers_count // 25)


def production_limit(site):
    capacity = max(0, site.max_storage - site.resource_stored)
    for resource, amount in production_rules(site).inputs_per_unit.items():
        capacity = min(capacity, max(0, site.input_stock.get(resource, 0)) // amount)
    return capacity


def produce(db, site, now):
    units, remainder = divmod(worker_rate(site) + site.production_remainder, 100)
    limit = production_limit(site)
    site.production_remainder = remainder if units < limit else 0
    units = min(units, limit)
    if not units:
        return
    consumed = {key: amount * units for key, amount in production_rules(site).inputs_per_unit.items()}
    site.input_stock = {key: amount - consumed.get(key, 0) for key, amount in site.input_stock.items()}
    site.resource_stored += units
    site.last_production_time = now
    record_daily(db, site, now, produced=units)


def settlement_candidates(db, enterprise_id=None):
    now = utc_now()
    legacy_cutoff = datetime.now() - SHIFT_DURATION
    query = select(User.id).outerjoin(EnterpriseShift, (
        (EnterpriseShift.worker_id == User.id) & (EnterpriseShift.status == "active")
    )).where(User.workplace.like("enterprise_%"), or_(
        EnterpriseShift.completes_at <= now,
        (EnterpriseShift.id.is_(None) & (User.work_start_time <= legacy_cutoff)),
    ))
    if enterprise_id is not None:
        query = query.where(User.workplace == f"enterprise_{enterprise_id}")
    return db.scalars(query.order_by(User.id)).all()


def settle_shift(db, worker_id, now=None):
    now = now or utc_now()
    db.execute(update(User).where(User.id == worker_id).values(workplace=User.workplace)
               .execution_options(synchronize_session=False))
    worker = db.get(User, worker_id, populate_existing=True)
    if worker is None or not worker.workplace or not worker.workplace.startswith("enterprise_"):
        return None
    shift = active_shift(db, worker.id)
    if shift is None:
        # Work begun before the migration used local timestamps and already reserved base pay.
        if not worker.work_start_time:
            return None
        started = worker.work_start_time.astimezone(timezone.utc).replace(tzinfo=None)
        completes = started + SHIFT_DURATION
    else:
        completes = shift.completes_at
    if completes > now:
        return None
    site_id = shift.enterprise_id if shift else int(worker.workplace.removeprefix("enterprise_"))
    site = lock_enterprise(db, site_id)
    if shift is None:
        base = max(0, site.salary)
        shift = EnterpriseShift(enterprise_id=site.id, worker_id=worker.id, started_at=started,
                                completes_at=completes, base_wage=base, multiplier_percent=100,
                                penalty_percent=0, payable=base, enterprise_payable=base)
        db.add(shift)
        record_daily(db, site, started)
    if shift.enterprise_payable is None:
        share = company_wage(shift.base_wage, shift.multiplier_percent, shift.penalty_percent)
        site.balance += shift.payable - share
        shift.enterprise_payable = share
    produce(db, site, now)
    worker.gold += shift.payable
    worker.workplace = worker.work_start_time = None
    site.workers_count = max(0, site.workers_count - 1)
    shift.status, shift.settled_at = "completed", now
    record_daily(db, site, now, wages=shift.payable)
    return {"type": "work_finished", "earned": shift.payable, "enterprise_name": site.name}


def previous_trade(db, worker_id, site_id, request_key, amount, target_id=None):
    if request_key is None:
        return False
    event = db.scalar(select(EnterpriseEvent).where(EnterpriseEvent.request_key == request_key))
    if event is None:
        return False
    if (event.actor_id, event.enterprise_id, event.details.get("quantity"), event.details.get("target")) != (
        worker_id, site_id, amount, target_id
    ):
        raise HTTPException(409, "Це підтвердження вже використано для іншої операції.")
    return True


def previous_employment(db, worker_id, site_id, request_key):
    if request_key is None:
        return False
    event = db.scalar(select(EnterpriseEvent).where(EnterpriseEvent.request_key == request_key))
    if event is None:
        return False
    if (event.kind, event.actor_id, event.enterprise_id) != ("employment", worker_id, site_id):
        raise HTTPException(409, "Це підтвердження вже використано для іншої операції.")
    return True


def can_procure(site, worker):
    return site.owner_id == worker.id or (site.owner_id == SYSTEM_PLAYER_ID and worker.is_admin)


def trade(db, seller, worker, amount, shown_price, shown_total, request_key, now, *, target=None):
    resource = seller.resource_type
    if resource not in resource_names() or amount < 1:
        raise HTTPException(422, "Ресурс або кількість недоступні для купівлі.")
    if target is not None:
        if target.id == seller.id or not can_procure(target, worker) or resource == target.resource_type:
            raise HTTPException(403, "Ця закупівля матеріалів недоступна.")
        if resource not in production_rules(target).inputs_per_unit:
            raise HTTPException(422, "Цей матеріал не потрібен підприємству.")
    if amount > seller.resource_stored:
        raise HTTPException(409, "На складі бракує ресурсу.")
    value = quote(seller, amount)
    if value["total"] > economy.MAX_GOLD or seller.balance + value["subtotal"] > economy.MAX_GOLD:
        raise HTTPException(422, "Сума операції перевищує допустимий ліміт.")
    if (shown_price, shown_total) != (value["unit_price"], value["total"]):
        return value
    if target is not None:
        current = target.input_stock.get(resource, 0)
        if value["total"] > target.balance or current + amount > economy.MAX_GOLD:
            raise HTTPException(400, "Недостатньо коштів або місця для закупівлі.")
        target.balance -= value["total"]
        target.input_stock = {**target.input_stock, resource: current + amount}
    else:
        if worker.gold < value["total"]:
            raise HTTPException(400, "Недостатньо золота.")
        worker.gold -= value["total"]
        if resource in LEGACY_BALANCES:
            setattr(worker, resource, getattr(worker, resource) + amount)
        else:
            balance = db.get(PlayerResourceBalance, (worker.id, resource))
            if balance is None:
                db.add(PlayerResourceBalance(player_id=worker.id, resource_id=resource, quantity=amount))
            else:
                balance.quantity += amount
        record_collection(db, worker.id, request_key, resource, amount)
    seller.resource_stored -= amount
    seller.balance += value["subtotal"]
    record_daily(db, seller, now, sold=amount, sale_gold=value["subtotal"])
    journal(db, seller, "sale", now, {"resource": resource, "quantity": amount, **value,
                                     "target": target.id if target else None}, worker.id, request_key)
    return None
