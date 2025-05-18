from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import database, models

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


def get_current_user(request: Request, db: Session = Depends(database.get_db)):
    username = request.cookies.get("username")
    if username:
        return db.query(models.User).filter(models.User.username == username).first()
    return None


@router.get("/admin/enterprises")
async def admin_enterprises(
    request: Request,
    db: Session = Depends(database.get_db),
    player: models.User = Depends(get_current_user),
):
    if not player or player.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")

    enterprises = db.query(models.Enterprise).all()
    return templates.TemplateResponse(
        "admin_enterprises.html",
        {"request": request, "player": player, "enterprises": enterprises},
    )


@router.post("/admin/enterprises/add")
async def add_enterprise(
    request: Request,
    name: str = Form(...),
    sector: str = Form(...),
    resource_type: str = Form(...),
    area: int = Form(...),
    storage_multiplier: int = Form(...),
    production_type: str = Form(...),
    salary: int = Form(...),
    item_price: int = Form(...),
    db: Session = Depends(database.get_db),
):
    # Перевіряємо чи адмін
    user = get_current_user(request, db)
    if not user or user.id != 1:
        raise HTTPException(status_code=403, detail="Not authorized")

    new_enterprise = models.Enterprise(
        name=name,
        sector=sector,
        resource_type=resource_type,
        area=area,
        storage_multiplier=storage_multiplier,
        production_type=production_type,
        salary=salary,
        item_price=item_price,
        max_workers=area * 3,  # Встановлюємо початкові значення
        max_storage=area * storage_multiplier,
    )

    db.add(new_enterprise)
    db.commit()

    return RedirectResponse(url="/admin/enterprises", status_code=303)


@router.post("/admin/enterprises/delete/{enterprise_id}")
async def delete_enterprise(
    enterprise_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")

    enterprise = (
        db.query(models.Enterprise)
        .filter(models.Enterprise.id == enterprise_id)
        .first()
    )
    if enterprise:
        db.delete(enterprise)
        db.commit()

    return RedirectResponse(url="/admin/enterprises", status_code=303)


@router.post("/admin/guild/edit-task/{task_id}")
async def edit_task(
    task_id: int,
    title: str = Form(...),
    description: str = Form(...),
    level_required: int = Form(...),
    order_in_scenario: int = Form(...),
    reward_gold: int = Form(0),
    reward_wood: int = Form(0),
    reward_stone: int = Form(0),
    reward_exp: int = Form(0),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Not authorized")

    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Оновлюємо дані завдання
    task.title = title
    task.description = description
    task.level_required = level_required
    task.order_in_scenario = order_in_scenario
    task.reward_gold = reward_gold
    task.reward_wood = reward_wood
    task.reward_stone = reward_stone
    task.reward_exp = reward_exp

    db.commit()

    return RedirectResponse(url="/admin/guild", status_code=303)


@router.get("/admin/guild")
async def admin_guild(
    request: Request,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")

    scenarios = db.query(models.QuestScenario).all()
    return templates.TemplateResponse(
        "admin/adventure_guild_form.html",
        {"request": request, "user": current_user, "scenarios": scenarios},
    )


@router.post("/admin/guild/add-scenario")
async def add_scenario(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    min_level: int = Form(...),
    is_active: bool = Form(True),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Not authorized")

    new_scenario = models.QuestScenario(
        title=title, description=description, min_level=min_level, is_active=is_active
    )

    db.add(new_scenario)
    db.commit()

    return RedirectResponse(url="/admin/guild", status_code=303)


@router.post("/admin/guild/add-task")
async def add_task(
    request: Request,
    scenario_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    level_required: int = Form(...),
    order_in_scenario: int = Form(...),
    reward_gold: int = Form(0),
    reward_wood: int = Form(0),
    reward_stone: int = Form(0),
    reward_exp: int = Form(0),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Not authorized")

    new_task = models.Task(
        scenario_id=scenario_id,
        title=title,
        description=description,
        level_required=level_required,
        order_in_scenario=order_in_scenario,
        reward_gold=reward_gold,
        reward_wood=reward_wood,
        reward_stone=reward_stone,
        reward_exp=reward_exp,
    )

    db.add(new_task)
    db.commit()

    return RedirectResponse(url="/admin/guild", status_code=303)


@router.post("/admin/guild/delete-task/{task_id}")
async def delete_task(
    task_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")

    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if task:
        db.delete(task)
        db.commit()

    return RedirectResponse(url="/admin/guild", status_code=303)


@router.post("/admin/guild/delete-scenario/{scenario_id}")
async def delete_scenario(
    scenario_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        raise HTTPException(status_code=403, detail="Access denied")

    scenario = (
        db.query(models.QuestScenario)
        .filter(models.QuestScenario.id == scenario_id)
        .first()
    )
    if scenario:
        # Спочатку видаляємо всі завдання сценарію та пов'язані user_tasks
        tasks = (
            db.query(models.Task).filter(models.Task.scenario_id == scenario_id).all()
        )
        for task in tasks:
            # Видаляємо всі user_tasks для цього завдання
            db.query(models.UserTask).filter(
                models.UserTask.task_id == task.id
            ).delete()
            # Видаляємо саме завдання
            db.delete(task)

        # Потім видаляємо сам сценарій
        db.delete(scenario)
        db.commit()

    return RedirectResponse(url="/admin/guild", status_code=303)
