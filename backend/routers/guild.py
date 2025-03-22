# from fastapi import APIRouter, Request, Depends, HTTPException
# from fastapi.responses import HTMLResponse, RedirectResponse
# from sqlalchemy.orm import Session
# from fastapi.templating import Jinja2Templates
# from backend.database import get_db
# from backend.models import User, Task, UserTask, QuestScenario
# from typing import List

# router = APIRouter()
# templates = Jinja2Templates(directory="frontend/templates")

# def get_current_user(request: Request, db: Session = Depends(get_db)):
#     username = request.cookies.get("username")
#     if username:
#         return db.query(User).filter(User.username == username).first()
#     return None

# @router.get("/guild")
# async def get_guild(
#     request: Request,
#     scenario_id: int = None,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     if not current_user:
#         return RedirectResponse(url="/")
    
#     # Отримуємо доступні сценарії для рівня користувача
#     scenarios = db.query(QuestScenario).filter(
#         QuestScenario.min_level <= current_user.level,
#         QuestScenario.is_active == True
#     ).all()
    
#     # Отримуємо завдання обраного сценарію
#     available_tasks = []
#     if scenario_id:
#         available_tasks = db.query(Task).filter(
#             Task.scenario_id == scenario_id
#         ).order_by(Task.order_in_scenario).all()
    
#     # Отримуємо завдання користувача
#     user_tasks = db.query(UserTask).filter(
#         UserTask.user_id == current_user.id
#     ).all()
    
#     completed_task_ids = [ut.task_id for ut in user_tasks if ut.is_completed]
#     in_progress_task_ids = [ut.task_id for ut in user_tasks if not ut.is_completed]
    
#     # Визначаємо статуси сценаріїв
#     completed_scenarios = set()
#     active_scenarios = set()
#     for scenario in scenarios:
#         scenario_tasks = [t.id for t in scenario.tasks]
#         if all(task_id in completed_task_ids for task_id in scenario_tasks):
#             completed_scenarios.add(scenario.id)
#         elif any(task_id in in_progress_task_ids for task_id in scenario_tasks):
#             active_scenarios.add(scenario.id)
    
#     return templates.TemplateResponse(
#         "guild.html",
#         {
#             "request": request,
#             "user": current_user,
#             "scenarios": scenarios,
#             "selected_scenario": scenario_id,
#             "available_tasks": available_tasks,
#             "completed_task_ids": completed_task_ids,
#             "in_progress_task_ids": in_progress_task_ids,
#             "completed_scenarios": completed_scenarios,
#             "active_scenarios": active_scenarios
#         }
#     ) 