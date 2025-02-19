from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from backend import models, database

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

def update_resources(db: Session):
    """Оновлює ресурси та зарплати"""
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.name == "sawmill").first()
    if not enterprise:
        return
    
    current_time = datetime.now()
    
    # Оновлюємо зарплати працівників
    workers = db.query(models.User).filter(models.User.workplace == "sawmill").all()
    for worker in workers:
        if worker.last_salary_time:
            minutes_passed = (current_time - worker.last_salary_time).total_seconds() / 60
            if minutes_passed >= 1:
                gold_earned = int(minutes_passed) * 3
                worker.gold += gold_earned
                worker.last_salary_time = current_time
    
    # Оновлюємо виробництво дерева
    if enterprise.last_production_time:
        minutes_passed = (current_time - enterprise.last_production_time).total_seconds() / 60
        if minutes_passed >= 1:
            wood_produced = int(minutes_passed) * enterprise.workers_count
            enterprise.resource_stored = min(666, enterprise.resource_stored + wood_produced)
            enterprise.last_production_time = current_time
    
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
        "sawmill.html",
        {
            "request": request,
            "user": user,
            "enterprise": enterprise,
            "is_working": user.workplace == f"sawmill_{enterprise.id}",
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
    
    if user.workplace:
        raise HTTPException(status_code=400, detail="Already working somewhere")
    
    # Перевірка 20-секундного таймауту після звільнення
    if user.last_quit_time:
        cooldown_time = datetime.now() - user.last_quit_time
        if cooldown_time.total_seconds() < 20:
            remaining_seconds = 20 - int(cooldown_time.total_seconds())
            raise HTTPException(status_code=400, detail=f"Please wait {remaining_seconds} seconds before starting new work")
    
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.id == enterprise_id).first()
    if not enterprise:
        raise HTTPException(status_code=404, detail="Enterprise not found")
    
    # Перевіряємо чи не досягнуто максимальної кількості працівників
    if enterprise.workers_count >= enterprise.max_workers:
        raise HTTPException(status_code=400, detail="Maximum workers limit reached")
    
    user.workplace = f"sawmill_{enterprise.id}"
    user.last_salary_time = datetime.now()
    enterprise.workers_count += 1
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
    
    if user.workplace != f"sawmill_{enterprise.id}":
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

@router.post("/enterprise/{enterprise_id}/buy-wood")
async def buy_wood(enterprise_id: int, request: Request, amount: int, db: Session = Depends(database.get_db)):
    user_session_id = request.cookies.get("session_id")
    if not user_session_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    enterprise = db.query(models.Enterprise).filter(models.Enterprise.name == "sawmill").first()
    
    total_cost = amount * enterprise.item_price
    if user.gold < total_cost:
        raise HTTPException(status_code=400, detail="Not enough gold")
    
    if enterprise.resource_stored < amount:
        raise HTTPException(
            status_code=400, 
            detail="Ой, на складі порожньо, влаштуйтесь на підприємство, щоб виготовити ресурси"
        )
    
    user.gold -= total_cost
    user.wood += amount
    enterprise.resource_stored -= amount
    
    db.commit()
    return {"status": "success"} 