from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import QuestScenario, Task, User, UserTask
from backend.routers.admin import get_current_user
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

@router.get("/guild")
async def get_guild(
    request: Request,
    scenario_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        return RedirectResponse(url="/")
    
    # Отримуємо доступні сценарії для рівня користувача
    scenarios = db.query(QuestScenario).filter(
        QuestScenario.min_level <= current_user.level,
        QuestScenario.is_active == True
    ).all()
    
    # Отримуємо завдання обраного сценарію
    available_tasks = []
    if scenario_id:
        available_tasks = db.query(Task).filter(
            Task.scenario_id == scenario_id
        ).order_by(Task.order_in_scenario).all()
    else:
        # Якщо сценарій не вибрано, показуємо всі доступні завдання для рівня користувача
        available_tasks = db.query(Task).filter(
            Task.level_required <= current_user.level,
            Task.scenario_id != None  # Тільки завдання, що належать сценаріям
        ).order_by(Task.order_in_scenario).all()
    
    # Отримуємо завдання користувача
    user_tasks = db.query(UserTask).filter(
        UserTask.user_id == current_user.id
    ).all()
    
    completed_task_ids = [ut.task_id for ut in user_tasks if ut.is_completed]
    in_progress_task_ids = [ut.task_id for ut in user_tasks if not ut.is_completed]
    
    # Визначаємо статуси сценаріїв
    completed_scenarios = set()
    active_scenarios = set()
    for scenario in scenarios:
        scenario_tasks = [t.id for t in scenario.tasks]
        if all(task_id in completed_task_ids for task_id in scenario_tasks):
            completed_scenarios.add(scenario.id)
        elif any(task_id in in_progress_task_ids for task_id in scenario_tasks):
            active_scenarios.add(scenario.id)
    
    return templates.TemplateResponse(
        "adventure_guild.html",
        {
            "request": request,
            "user": current_user,
            "scenarios": scenarios,
            "selected_scenario": scenario_id,
            "available_tasks": available_tasks,
            "completed_task_ids": completed_task_ids,
            "in_progress_task_ids": in_progress_task_ids,
            "completed_scenarios": completed_scenarios,
            "active_scenarios": active_scenarios
        }
    )

@router.post("/guild/accept-task/{task_id}")
async def accept_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Перевіряємо чи існує завдання
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Перевіряємо чи відповідає рівень користувача
    if current_user.level < task.level_required:
        raise HTTPException(status_code=403, detail="Level too low")
    
    # Перевіряємо чи не взяте вже це завдання
    existing_task = db.query(UserTask).filter(
        UserTask.user_id == current_user.id,
        UserTask.task_id == task_id
    ).first()
    
    if existing_task:
        raise HTTPException(status_code=400, detail="Task already accepted")
    
    # Створюємо нове завдання для користувача
    user_task = UserTask(
        user_id=current_user.id,
        task_id=task_id,
        is_completed=False
    )
    
    db.add(user_task)
    db.commit()
    
    return RedirectResponse(url=f"/guild?scenario={task.scenario_id}", status_code=303) 