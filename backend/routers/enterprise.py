from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.auth import session_player
from backend import database, models
from backend.services.activity_guilds import WORKERS, award_point
from backend.services.guild import record_collection
from backend.services.world import require_presence

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def update_resources(db: Session):
    """Оновлює ресурси та зарплати"""
    enterprises = db.query(models.Enterprise).all()
    current_time = datetime.now()

    for enterprise in enterprises:
        # Оновлюємо максимальну кількість працівників (площа * 3)
        enterprise.max_workers = enterprise.area * 3

        # Оновлюємо максимальний розмір складу
        enterprise.max_storage = enterprise.area * enterprise.storage_multiplier

        if enterprise.last_production_time:
            hours_passed = (
                current_time - enterprise.last_production_time
            ).total_seconds() / 3600
            if hours_passed >= 1:
                # Бонус від кількості працівників (1% за кожні 25 працівників)
                worker_bonus = 1 + (enterprise.workers_count // 25) * 0.01

                # Розраховуємо базову продуктивність залежно від типу виробництва
                if enterprise.production_type == "mine":
                    # Для шахт: 1 ресурс на працівника за годину
                    base_production = enterprise.workers_count
                else:
                    # Для заводів: 1 ресурс * площа на працівника за годину
                    base_production = enterprise.workers_count * enterprise.area

                # Розраховуємо загальне виробництво
                resources_produced = int(hours_passed * base_production * worker_bonus)

                # Перевіряємо ліміт складу
                new_resource_amount = min(
                    enterprise.max_storage,
                    enterprise.resource_stored + resources_produced,
                )
                enterprise.resource_stored = new_resource_amount
                enterprise.last_production_time = current_time

        # Оновлюємо зарплати працівників
        workers = (
            db.query(models.User)
            .filter(models.User.workplace == f"enterprise_{enterprise.id}")
            .all()
        )

        for worker in workers:
            if worker.work_start_time:
                hours_worked = (
                    current_time - worker.work_start_time
                ).total_seconds() / 3600

                # Якщо пройшла година, нараховуємо зарплату і звільняємо
                if hours_worked >= 1:
                    # Нараховуємо зарплату за годину
                    gold_earned = enterprise.salary
                    worker.gold += gold_earned
                    enterprise.balance -= gold_earned

                    # Звільняємо працівника
                    worker.workplace = None
                    worker.work_start_time = None
                    enterprise.workers_count -= 1

    db.commit()


@router.get("/enterprise/{enterprise_id}", response_class=HTMLResponse)
async def enterprise_page(
    enterprise_id: int, request: Request, db: Session = Depends(database.get_db)
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = session_player(request, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    enterprise = (
        db.query(models.Enterprise)
        .filter(models.Enterprise.id == enterprise_id)
        .first()
    )
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    require_presence(db, user, enterprise.sector)

    # Отримуємо список всіх працівників підприємства
    workers = (
        db.query(models.User)
        .filter(models.User.workplace == f"enterprise_{enterprise.id}")
        .all()
    )

    # Release the player lock before production updates other players' balances.
    db.commit()
    update_resources(db)
    require_presence(db, user, enterprise.sector)
    db.commit()

    return templates.TemplateResponse(
        "enterprise.html",
        {
            "request": request,
            "user": user,
            "enterprise": enterprise,
            "workers": workers,
            "current_time": datetime.now(),
            "timedelta": timedelta,
        },
    )


@router.post("/enterprise/{enterprise_id}/start-work")
async def start_work(
    enterprise_id: int, request: Request, db: Session = Depends(database.get_db)
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = session_player(request, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    enterprise = (
        db.query(models.Enterprise)
        .filter(models.Enterprise.id == enterprise_id)
        .first()
    )
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    require_presence(db, user, enterprise.sector)

    current_time = datetime.now()

    if user.workplace:
        raise HTTPException(status_code=400, detail="Already working somewhere")

    if enterprise.workers_count >= enterprise.max_workers:
        raise HTTPException(status_code=400, detail="No vacant positions")

    # Розраховуємо зарплату за годину
    salary_for_hour = enterprise.salary

    # Перевіряємо, чи вистачає балансу на зарплату
    if enterprise.balance < salary_for_hour:
        raise HTTPException(
            status_code=400, detail="Enterprise doesn't have enough money to pay salary"
        )

    result = db.execute(
        update(models.Enterprise).where(
            models.Enterprise.id == enterprise_id,
            models.Enterprise.workers_count < models.Enterprise.max_workers,
            models.Enterprise.balance >= salary_for_hour,
            models.Enterprise.salary == salary_for_hour,
            models.Enterprise.sector == user.map_sector,
        ).values(
            balance=models.Enterprise.balance - salary_for_hour,
            workers_count=models.Enterprise.workers_count + 1,
        )
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Умови працевлаштування змінилися.")

    user.workplace = f"enterprise_{enterprise.id}"
    user.work_start_time = current_time
    award_point(db, user.id, WORKERS)
    db.commit()
    return {"status": "success"}


# Додаємо модель для запиту
class buyResources(BaseModel):
    amount: int


@router.post("/enterprise/{enterprise_id}/buy-resources")
async def buy_resources(
    enterprise_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
    amount: int = Form(..., gt=0, le=2_147_483_647),
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")

    user = session_player(request, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    enterprise = (
        db.query(models.Enterprise)
        .filter(models.Enterprise.id == enterprise_id)
        .first()
    )
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    require_presence(db, user, enterprise.sector)

    total_cost = amount * enterprise.item_price
    if not 0 <= total_cost <= 2_147_483_647:
        raise HTTPException(status_code=422, detail="Invalid purchase total")

    resource = enterprise.resource_type
    record_collection(db, user.id, uuid4().hex, resource, amount)

    wallet = {"gold": models.User.gold - total_cost}
    if resource == "gold":
        wallet["gold"] += amount
    elif resource in {"singing_resin", "basalt_bone"}:
        wallet[resource] = getattr(models.User, resource) + amount
    result = db.execute(
        update(models.User).where(models.User.id == user.id, models.User.gold >= total_cost)
        .values(**wallet)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=400, detail="Not enough gold")

    result = db.execute(
        update(models.Enterprise).where(
            models.Enterprise.id == enterprise_id,
            models.Enterprise.resource_stored >= amount,
            models.Enterprise.item_price == enterprise.item_price,
            models.Enterprise.resource_type == resource,
        ).values(
            balance=models.Enterprise.balance + total_cost,
            resource_stored=models.Enterprise.resource_stored - amount,
        )
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="Enterprise stock or price changed")

    db.commit()
    return RedirectResponse(url=f"/enterprise/{enterprise_id}", status_code=303)


# @router.post("/move-to-sector")
# async def move_to_sector(
#     request: Request,
#     movement: dict,
#     db: Session = Depends(database.get_db)
# ):
#     user_session_id = request.cookies.get("session_id")
#     if not user_session_id:
#         raise HTTPException(status_code=401, detail="Not logged in")

#     user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # Перевіряємо, чи не працює зараз гравець
#     if user.workplace and user.work_start_time:
#         hours_worked = (datetime.now() - user.work_start_time).total_seconds() / 3600
#         if hours_worked < 8:
#             raise HTTPException(status_code=400, detail="You cannot leave sector while working! (8 hours not passed)")

#     sector = str(movement.get("sector"))
#     x = movement.get("x")
#     y = movement.get("y")

#     if sector in ["Mountain", "Castle", "Forest"] and x is not None and y is not None:
#         user.map_sector = sector
#         user.map_x = x
#         user.map_y = y
#         db.commit()

#     return {"status": "success"}
