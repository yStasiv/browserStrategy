from datetime import date, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import database, models
from backend.auth import session_player
from backend.services import economy, enterprises
from backend.services.world import require_presence, utc_now

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def context(request, db, enterprise_id):
    user = session_player(request, db)
    if user is None:
        raise HTTPException(401, "Увійди до гри.")
    site = db.get(models.Enterprise, enterprise_id)
    if site is None:
        raise HTTPException(404, "Підприємство не знайдено.")
    require_presence(db, user, site.sector)
    return user, site


def render(request, db, user, site, *, before=None, confirmation=None, error=None, status=200):
    now = utc_now()
    names = enterprises.resource_names()
    report = models.EnterpriseDailyReport
    history = select(report).where(report.enterprise_id == site.id, report.day < enterprises.reporting_day(now))
    if before is not None:
        history = history.where(report.day < before)
    history = db.scalars(history.order_by(report.day.desc()).limit(21)).all()
    workers = db.scalars(select(models.User).where(
        models.User.workplace == f"enterprise_{site.id}",
    ).order_by(models.User.username)).all()
    shift = enterprises.active_shift(db, user.id)
    end = shift.completes_at if shift else None
    started = shift.started_at if shift else None
    displayed_wage = enterprises.wage(site)
    if shift is not None and shift.enterprise_id == site.id:
        displayed_wage = shift
    if shift is None and user.work_start_time:
        started = user.work_start_time.astimezone(timezone.utc).replace(tzinfo=None)
        end = started + enterprises.SHIFT_DURATION
        if user.workplace == f"enterprise_{site.id}":
            base = max(0, site.salary)
            displayed_wage = dict(base_wage=base, multiplier_percent=100, penalty_percent=0, payable=base)
    projected = enterprises.worker_rate(site) * site.workers_count // 100
    estimate = min(enterprises.production_limit(site), projected)
    wages_in_progress = db.scalars(select(func.coalesce(models.EnterpriseShift.enterprise_payable,
                                                       models.EnterpriseShift.payable)).where(
        models.EnterpriseShift.enterprise_id == site.id, models.EnterpriseShift.status == "active",
    )).all()
    production = enterprises.production_rules(site)
    inputs = []
    for key, per_unit in production.inputs_per_unit.items():
        suppliers = db.scalars(select(models.Enterprise).where(
            models.Enterprise.id != site.id, models.Enterprise.sector == site.sector,
            models.Enterprise.resource_type == key, models.Enterprise.resource_stored > 0,
        ).order_by(models.Enterprise.name)).all()
        if not enterprises.can_procure(site, user):
            sellers = []
        else:
            sellers = [{"site": seller, "price": enterprises.price(seller), "key": uuid4()} for seller in suppliers]
        available = site.input_stock.get(key, 0)
        consumption = per_unit * projected
        inputs.append(dict(name=names[key], per_unit=per_unit, available=available, consumption=consumption,
                           missing=max(0, consumption - available), sellers=sellers,
                           price=min((enterprises.price(seller) for seller in suppliers), default=None)))
    return templates.TemplateResponse("enterprise.html", {
        "request": request, "user": user, "enterprise": site, "workers": workers,
        "current_time": now, "shift_start": started, "shift_end": end,
        "wage": displayed_wage,
        "employment_error": enterprises.employment_error(db, site, user),
        "hourly_wages": sum(wages_in_progress) + max(0, site.workers_count - len(wages_in_progress)) * site.salary,
        "hourly_output": estimate, "unit_price": enterprises.price(site),
        "commission_percent": economy.GOLD_COMMISSION_PERCENT, "request_key": uuid4(),
        "employment_key": uuid4(), "image_url": enterprises.image_url(site),
        "resource_names": names, "inputs": inputs, "history": history[:20],
        "hires_by_day": enterprises.daily_hires(db, site.id, {row.day for row in history[:20]}),
        "next_history": history[19].day.isoformat() if len(history) > 20 else None,
        "confirmation": confirmation, "action_error": error,
    }, status_code=status)


@router.get("/enterprise/{enterprise_id}", response_class=HTMLResponse)
def enterprise_page(enterprise_id: int, request: Request, before: date | None = Query(None),
                    db: Session = Depends(database.get_db)):
    context(request, db, enterprise_id)
    db.commit()
    overdue = enterprises.settlement_candidates(db, enterprise_id)
    db.commit()
    for worker_id in overdue:
        enterprises.settle_shift(db, worker_id)
        db.commit()
    user, site = context(request, db, enterprise_id)
    db.commit()
    return render(request, db, user, site, before=before)


@router.post("/enterprise/{enterprise_id}/start-work")
def start_work(enterprise_id: int, request: Request, db: Session = Depends(database.get_db),
               return_to_enterprise: bool = Form(False), request_key: UUID | None = Form(None)):
    user, _ = context(request, db, enterprise_id)
    key = str(request_key) if request_key else None
    if enterprises.previous_employment(db, user.id, enterprise_id, key):
        return RedirectResponse(f"/enterprise/{enterprise_id}", status_code=303)
    if user.workplace:
        if enterprises.settle_shift(db, user.id):
            db.commit()
            user, _ = context(request, db, enterprise_id)
            if enterprises.previous_employment(db, user.id, enterprise_id, key):
                return RedirectResponse(f"/enterprise/{enterprise_id}", status_code=303)
    site = enterprises.lock_enterprise(db, enterprise_id)
    try:
        if site.sector != user.map_sector:
            raise HTTPException(403, "Підприємство має бути в поточному секторі.")
        enterprises.start_shift(db, site, user, utc_now(), key)
        db.commit()
    except HTTPException as exc:
        if not return_to_enterprise:
            raise
        db.rollback()
        return render(request, db, user, site, error=exc.detail, status=exc.status_code)
    if return_to_enterprise:
        return RedirectResponse(f"/enterprise/{site.id}", status_code=303)
    return {"status": "success"}


@router.post("/enterprise/{enterprise_id}/buy-resources")
@router.post("/enterprise/{enterprise_id}/procure-input")
def buy_resources(
    enterprise_id: int, request: Request, db: Session = Depends(database.get_db),
    amount: int = Form(..., gt=0, le=economy.MAX_GOLD),
    expected_price: int | None = Form(None, ge=0),
    expected_total: int | None = Form(None),
    request_key: UUID | None = Form(None),
    supplier_id: int | None = Form(None, gt=0),
):
    user, site = context(request, db, enterprise_id)
    procuring = request.url.path.endswith("/procure-input")
    target_id = enterprise_id if procuring else None
    seller_id = supplier_id if procuring else enterprise_id
    key = str(request_key or uuid4())
    if seller_id is None or (procuring and (not enterprises.can_procure(site, user) or seller_id == target_id)):
        raise HTTPException(403, "Ця закупівля матеріалів недоступна.")
    if enterprises.previous_trade(db, user.id, seller_id, key, amount, target_id):
        return RedirectResponse(f"/enterprise/{enterprise_id}", status_code=303)
    try:
        locked = {identifier: enterprises.lock_enterprise(db, identifier)
                  for identifier in sorted({seller_id, enterprise_id})}
        seller = locked[seller_id]
        target = locked[target_id] if procuring else None
        if seller.sector != user.map_sector or (target and target.sector != user.map_sector):
            raise HTTPException(403, "Постачальник має бути в поточному секторі.")
        confirmation = enterprises.trade(
            db, seller, user, amount, expected_price, expected_total if request_key else None,
            key, utc_now(), target=target,
        )
        if confirmation is None:
            db.commit()
            return RedirectResponse(f"/enterprise/{enterprise_id}", status_code=303)
        details = {**confirmation, "amount": amount, "request_key": key, "supplier_id": supplier_id,
                   "resource": seller.resource_type, "procurement": procuring,
                   "changed": request_key is not None and expected_price is not None}
        db.rollback()
        return render(request, db, user, site, confirmation=details, status=409)
    except HTTPException as exc:
        db.rollback()
        return render(request, db, user, site, error=exc.detail, status=exc.status_code)
    except IntegrityError:
        db.rollback()
        if enterprises.previous_trade(db, user.id, seller_id, key, amount, target_id):
            return RedirectResponse(f"/enterprise/{enterprise_id}", status_code=303)
        raise
