from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.auth import get_current_user as session_user
from backend.services import guild
from backend.database import get_db
from backend.models import QuestScenario, Task, User, UserTask

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    user = await session_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Увійдіть до гри.")
    return user


router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/guild/scenarios")
async def get_guild(
    request: Request,
    scenario_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Перевіряємо чи користувач в секторі Castle
    if current_user.map_sector != "Castle":
        return templates.TemplateResponse(
            "adventure_guild.html",
            {
                "request": request,
                "user": current_user,
                "error": "Гільдія авантюристів доступна тільки в секторі Castle",
            },
        )

    # Перевіряємо чи виконане перше завдання
    first_task_completed = (
        db.query(UserTask)
        .filter(
            UserTask.user_id == current_user.id,
            UserTask.task_id == 1,
            UserTask.is_completed == True,
        )
        .first()
        is not None
    )

    # Якщо перше завдання не виконане, показуємо тільки перший сценарій і перше завдання
    if not first_task_completed:
        scenario = db.query(QuestScenario).filter(QuestScenario.id == 1).first()
        task = db.query(Task).filter(Task.id == 1).first()

        return templates.TemplateResponse(
            "adventure_guild.html",
            {
                "request": request,
                "user": current_user,
                "scenarios": [scenario] if scenario else [],
                "selected_scenario": 1,
                "available_tasks": [task] if task else [],
                "completed_task_ids": [],
                "in_progress_task_ids": [1],
                "completed_scenarios": set(),
                "active_scenarios": set([1]) if scenario else set(),
            },
        )

    # Якщо перше завдання виконане, показуємо всі доступні сценарії та завдання
    scenarios = (
        db.query(QuestScenario)
        .filter(
            QuestScenario.min_level <= current_user.level,
            QuestScenario.is_active == True,
        )
        .all()
    )

    # Отримуємо завдання обраного сценарію
    available_tasks = []
    if scenario_id:
        available_tasks = (
            db.query(Task)
            .filter(Task.scenario_id == scenario_id)
            .order_by(Task.order_in_scenario)
            .all()
        )
    else:
        # Якщо сценарій не вибрано, показуємо всі доступні завдання для рівня користувача
        available_tasks = (
            db.query(Task)
            .filter(
                Task.level_required <= current_user.level,
                Task.scenario_id != None,  # Тільки завдання, що належать сценаріям
            )
            .order_by(Task.order_in_scenario)
            .all()
        )

    # Отримуємо завдання користувача
    user_tasks = db.query(UserTask).filter(UserTask.user_id == current_user.id).all()

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

    response = templates.TemplateResponse(
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
            "active_scenarios": active_scenarios,
        },
    )

    # Позначаємо що користувач відвідав гільдію
    response.set_cookie(key="visited_guild", value="true")

    return response


@router.post("/guild/accept-task/{task_id}")
async def accept_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.map_sector != "Castle":
        raise HTTPException(status_code=403, detail="Гільдія доступна тільки в секторі Castle.")

    # Перевіряємо чи існує завдання
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Перевіряємо чи відповідає рівень користувача
    if current_user.level < task.level_required:
        raise HTTPException(status_code=403, detail="Level too low")

    # Перевіряємо чи не взяте вже це завдання
    existing_task = (
        db.query(UserTask)
        .filter(UserTask.user_id == current_user.id, UserTask.task_id == task_id)
        .first()
    )

    if existing_task:
        raise HTTPException(status_code=400, detail="Task already accepted")

    # Створюємо нове завдання для користувача
    user_task = UserTask(user_id=current_user.id, task_id=task_id, is_completed=False)

    db.add(user_task)
    db.commit()

    return RedirectResponse(url=f"/guild/scenarios?scenario_id={task.scenario_id}", status_code=303)


class ReplaceQuest(BaseModel):
    confirm_progress_loss: bool = False


@router.get("/guild")
async def guild_page(request: Request, db: Session = Depends(get_db)):
    user = await session_user(request, db)
    if user is None:
        return RedirectResponse(url="/")
    response = templates.TemplateResponse(
        "guild_board.html", {"request": request, "user": user, "in_castle": user.map_sector == "Castle"}
    )
    if user.map_sector == "Castle":
        response.set_cookie("visited_guild", "true")
    return response


def require_castle(user):
    if user.map_sector != "Castle":
        raise HTTPException(status_code=403, detail="Гільдія доступна тільки в секторі Castle.")


def mutate_board(db, user, operation, *args):
    require_castle(user)
    try:
        operation(db, user.id, *args)
        db.flush()
        result = guild.board(db, user.id)
        db.commit()
    except guild.GuildError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return result


@router.get("/api/guild")
def guild_board(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_castle(user)
    return guild.board(db, user.id)


@router.post("/api/guild/initialize")
def initialize_board(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return mutate_board(db, user, guild.initialize)


@router.post("/api/guild/quests/{quest_id}/claim")
def claim_quest(quest_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return mutate_board(db, user, guild.claim, quest_id)


@router.post("/api/guild/quests/{quest_id}/replace")
def replace_quest(
    quest_id: int, body: ReplaceQuest, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return mutate_board(db, user, guild.replace, quest_id, body.confirm_progress_loss)
