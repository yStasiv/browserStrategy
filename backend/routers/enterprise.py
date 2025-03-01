from fastapi import APIRouter, HTTPException, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from backend import models, database
from pydantic import BaseModel

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
            hours_passed = (current_time - enterprise.last_production_time).total_seconds() / 3600
            if hours_passed >= 1:
                # Бонус від кількості працівників (1% за кожні 25 працівників)
                worker_bonus = 1 + (enterprise.workers_count // 25) * 0.01
                
                # Розраховуємо базову продуктивність залежно від типу виробництва
                if enterprise.production_type == 'mine':
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
                    enterprise.resource_stored + resources_produced
                )
                enterprise.resource_stored = new_resource_amount
                enterprise.last_production_time = current_time
        
        # Оновлюємо зарплати працівників
        workers = db.query(models.User).filter(
            models.User.workplace == f"enterprise_{enterprise.id}"
        ).all()
        
        for worker in workers:
            if worker.work_start_time:
                hours_worked = (current_time - worker.work_start_time).total_seconds() / 3600
                
                # Якщо пройшло 8 годин, нараховуємо зарплату і звільняємо
                if hours_worked >= 8:
                    # Нараховуємо зарплату за 8 годин
                    gold_earned = int(8 * enterprise.salary)  # 8 годин * ставка за годину
                    worker.gold += gold_earned
                    
                    # Звільняємо працівника
                    worker.workplace = None
                    worker.work_start_time = None
                    worker.last_quit_time = current_time
                    enterprise.workers_count -= 1
    
    db.commit()

@router.get("/enterprise/{enterprise_id}", response_class=HTMLResponse)
async def enterprise_page(enterprise_id: int, request: Request, db: Session = Depends(database.get_db)):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    
    # Отримуємо список всіх працівників підприємства
    workers = db.query(models.User).filter(
        models.User.workplace == f"enterprise_{enterprise.id}"
    ).all()
    
    update_resources(db)
    
    return templates.TemplateResponse(
        "enterprise.html",
        {
            "request": request,
            "user": user,
            "enterprise": enterprise,
            "workers": workers,
            "current_time": datetime.now(),
            "timedelta": timedelta
        }
    )

@router.post("/enterprise/{enterprise_id}/start-work")
async def start_work(enterprise_id: int, request: Request, db: Session = Depends(database.get_db)):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    
    current_time = datetime.now()
    
    # Перевіряємо, чи працював сьогодні
    if user.last_work_day and user.last_work_day.date() == current_time.date():
        raise HTTPException(status_code=400, detail="You can only work once per day!")
    
    if user.workplace:
        raise HTTPException(status_code=400, detail="Already working somewhere")
    
    if enterprise.workers_count >= enterprise.max_workers:
        raise HTTPException(status_code=400, detail="No vacant positions")
    
    # Перевіряємо, чи знаходиться гравець у правильному секторі
    if user.map_sector != enterprise.sector:
        raise HTTPException(status_code=400, detail="You must be in the same sector as the enterprise")
    
    # Розраховуємо кількість ресурсів, які будуть вироблені за зміну
    productivity_bonus = 1 + (enterprise.workers_count // 25) * 0.01
    resources_per_shift = int(8 * productivity_bonus)  # 8 годин бонус продуктивності
    
    # Перевіряємо, чи вистачить місця на складі
    space_needed = resources_per_shift
    space_available = enterprise.max_storage - enterprise.resource_stored
    
    if space_needed > space_available:
        raise HTTPException(
            status_code=400, 
            detail=f"На складі недостатньо місця. Потрібно: {space_needed}, доступно: {space_available}"
        )
    
    # Розраховуємо зарплату за зміну
    salary_for_shift = 8 * enterprise.salary  # 8 годин * ставка за годину
    
    # Перевіряємо, чи вистачає балансу на зарплату
    if enterprise.balance < salary_for_shift:
        raise HTTPException(status_code=400, detail="Enterprise doesn't have enough money to pay salary")
    
    # Знімаємо зарплату з балансу підприємства одразу
    enterprise.balance -= salary_for_shift
    
    user.workplace = f"enterprise_{enterprise.id}"
    user.work_start_time = current_time
    user.last_work_day = current_time
    enterprise.workers_count += 1
    
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
    amount: int = Form(...)
):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")

    total_cost = amount * enterprise.item_price
    
    if user.gold < total_cost:
        raise HTTPException(status_code=400, detail="Not enough gold")
    
    if enterprise.resource_stored < amount:
        raise HTTPException(status_code=400, detail="Not enough resources in storage")

    # Віднімаємо золото у користувача і додаємо на баланс підприємства
    user.gold -= total_cost
    enterprise.balance += total_cost
    
    # Віднімаємо ресурси зі складу
    enterprise.resource_stored -= amount
    
    # Додаємо ресурси користувачу
    if enterprise.resource_type == 'wood':
        user.wood += amount
    elif enterprise.resource_type == 'stone':
        user.stone += amount
    elif enterprise.resource_type == 'gold':
        user.gold += amount

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



