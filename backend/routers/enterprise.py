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
        # Оновлюємо зарплати працівників та виробництво ресурсів
        if enterprise.last_production_time:
            minutes_passed = (current_time - enterprise.last_production_time).total_seconds() / 60
            if minutes_passed >= 1:
                # Кожен працівник виробляє 1 ресурс за хвилину
                resources_produced = int(minutes_passed) * enterprise.workers_count
                # Перевіряємо, щоб не перевищити максимальну місткість складу
                new_resource_amount = min(
                    enterprise.max_storage,
                    enterprise.resource_stored + resources_produced
                )
                enterprise.resource_stored = new_resource_amount
                enterprise.last_production_time = current_time
        else:
            enterprise.last_production_time = current_time

        # Оновлюємо зарплати працівників
        workers = db.query(models.User).filter(
            models.User.workplace == f"enterprise_{enterprise.id}"
        ).all()
        
        for worker in workers:
            if worker.last_salary_time:
                minutes_passed = (current_time - worker.last_salary_time).total_seconds() / 60
                if minutes_passed >= 1:
                    gold_earned = int(minutes_passed) * enterprise.salary
                    worker.gold += gold_earned
                    worker.last_salary_time = current_time
    
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
    
    update_resources(db)
    
    return templates.TemplateResponse(
        "enterprise.html",
        {
            "request": request,
            "user": user,
            "enterprise": enterprise,
            # "is_working": user.workplace == f"enterprise_{enterprise.id}",
            "last_quit_time": user.last_quit_time.isoformat() if user.last_quit_time else None
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
    
    if user.workplace:
        raise HTTPException(status_code=400, detail="Already working somewhere")
    
    if enterprise.workers_count >= enterprise.max_workers:
        raise HTTPException(status_code=400, detail="No vacant positions")
    
    # Перевіряємо кулдаун
    if user.last_quit_time:
        cooldown_time = datetime.now() - user.last_quit_time
        if cooldown_time.total_seconds() < 20:  # 20 секунд кулдауну
            raise HTTPException(status_code=400, detail="You must wait before starting new work")
    
    user.workplace = f"enterprise_{enterprise.id}"
    user.last_salary_time = datetime.now()
    enterprise.workers_count += 1
    
    # Встановлюємо час початку виробництва, якщо це перший працівник
    if enterprise.workers_count == 1:
        enterprise.last_production_time = datetime.now()
    
    db.commit()
    return {"status": "success"}

@router.post("/enterprise/{enterprise_id}/quit-work")
async def quit_work(enterprise_id: int, request: Request, db: Session = Depends(database.get_db)):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    
    if user.workplace != f"enterprise_{enterprise.id}":
        raise HTTPException(status_code=400, detail="Not working at this enterprise")
    
    # Нараховуємо зарплату при звільненні
    current_time = datetime.now()
    if user.last_salary_time:
        minutes_worked = (current_time - user.last_salary_time).total_seconds() / 60
        gold_earned = int(minutes_worked * enterprise.salary)
        user.gold += gold_earned
    
    user.workplace = None
    user.last_salary_time = None
    user.last_quit_time = current_time  # Зберігаємо час звільнення
    enterprise.workers_count -= 1
    
    db.commit()
    return {"status": "success", "gold_earned": gold_earned}

# Додаємо модель для запиту
class buyResources(BaseModel):
    amount: int

# @router.post("/enterprise/{enterprise_id}/buy-wood")
# async def buy_wood(
#     enterprise_id: int, 
#     request: Request, 
#     buy_request: buyResources,
#     db: Session = Depends(database.get_db)
# ):
#     user_session_id = request.cookies.get("session_id")
#     if not user_session_id:
#         raise HTTPException(status_code=401, detail="Not logged in")
    
#     user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
    
#     enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
#     if not enterprise:
#         raise HTTPException(status_code=404, detail="Enterprise not found")
    
#     # Використовуємо amount з моделі запиту
#     amount = buy_request.amount
#     total_cost = amount * enterprise.item_price
    
#     if user.gold < total_cost:
#         raise HTTPException(status_code=400, detail="Not enough gold")
    
#     if enterprise.resource_stored < amount:
#         raise HTTPException(
#             status_code=400, 
#             detail="Ой, на складі порожньо, влаштуйтесь на підприємство, щоб виготовити ресурси"
#         )
    
#     user.gold -= total_cost
#     user.wood += amount
#     enterprise.resource_stored -= amount
    
#     db.commit()
#     return {"status": "success"}

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

    # Віднімаємо золото і додаємо ресурси
    user.gold -= total_cost
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



