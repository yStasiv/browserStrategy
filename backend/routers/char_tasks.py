from fastapi import APIRouter, HTTPException, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from backend import models, database, utils
from backend.routers.character import CharacterHelper

logger = utils.setup_logger(__name__)


router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class TaskHelper:


    @staticmethod
    def update_tasks_for_users(db: Session, db_task: models.Task, all_users: list[models.User]) -> None:
         # Add this task for each users
        for user in all_users: 
            user_task = models.UserTask(user_id=user.id, task_id=db_task.id) 
            db.add(user_task) 
        db.commit()

    @staticmethod
    def create_task(
            db: Session, 
            title: str, 
            description: str, 
            level_required: int, 
            reward_gold: int, 
            reward_wood: int, 
            reward_stone: int, 
            reward_exp: int
        ) -> models.Task:
        """Create new task with rewards for each user"""
        for reward in [reward_gold, reward_wood, reward_stone, reward_exp]:
            try:
                reward = int(reward)
            except TypeError:
                reward = 0
        db_task = models.Task(
            title=title, 
            description=description, 
            level_required=level_required, 
            reward_gold=reward_gold, 
            reward_wood=reward_wood, 
            reward_stone=reward_stone, 
            reward_exp=reward_exp
            )       
        db.add(db_task)
        db.commit()
        db.refresh(db_task)

        # Add this task for each users
        TaskHelper.update_tasks_for_users(db, db_task, all_users=db.query(models.User).all() )
        return db_task

    @staticmethod
    def get_all_tasks(db: Session):
        return db.query(models.Task).all()
    
    @staticmethod 
    def get_available_tasks_for_user(db: Session, user: models.User): 
        tasks = db.query(models.UserTask).join(models.Task).filter( models.UserTask.user_id == user.id, models.Task.level_required <= user.level ).all()
        if user.id == 1:
            tasks = db.query(models.UserTask).join(models.Task).filter( models.UserTask.user_id == user.id).all()
        return tasks
    
    @staticmethod 
    def update_task_completion(db: Session, user_id: int, task_id: int, is_completed: bool): 
        user_task = db.query(models.UserTask).filter(models.UserTask.user_id == user_id, models.UserTask.task_id == task_id ).first() 
        if user_task: 
            user_task.is_completed = is_completed 
            db.commit() 

            # Give reward for task
            task = db.query(models.Task).filter(models.Task.id == task_id).first() 
            if task and is_completed: 
                reward_exp = TaskHelper.give_reward(db, user_id, task)
                if reward_exp:
                    logger.info(f"Task retun some exp {reward_exp}, let up user lvl if needed")
                    user = db.query(models.User).filter(models.User.id == user_id).first() 
                    if user: 
                        CharacterHelper.update_user_level(user, db)

            return user_task 
        else: 
            raise HTTPException(status_code=404, detail="User task not found")
        
    @staticmethod
    def give_reward(db: Session, user_id: int, task: models.Task): 
        user = db.query(models.User).filter(models.User.id == user_id).first() 
        if user:
            user.gold += task.reward_gold 
            user.wood += task.reward_wood 
            user.stone += task.reward_stone 
            user.experience += task.reward_exp 

            db.commit()
        return task.reward_exp
    

class TaskRoutes(TaskHelper):
    @router.get("/char_tasks")
    async def get_tasks(
        request: Request,
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(database.get_current_user)
    ):
        if not current_user:
            return RedirectResponse(url="/login")
        
        user_tasks = TaskHelper.get_available_tasks_for_user(db, current_user)
        
        # Перевіряємо чи відвідував користувач гільдію
        has_visited_guild = request.cookies.get("visited_guild", "false") == "true"
        
        return templates.TemplateResponse(
            "char_tasks.html",
            {
                "request": request,
                "user": current_user,
                "user_tasks": user_tasks,
                "has_visited_guild": has_visited_guild
            }
        )

    @router.post("/char_tasks/add", response_class=RedirectResponse)
    async def add_task(
        request: Request,
        title: str = Form(...),
        description: str = Form(...),
        level_required: int = Form(...),
        reward_gold: int = Form(...), 
        reward_wood: int = Form(...), 
        reward_stone: int = Form(...), 
        reward_exp: int = Form(...),
        db: Session = Depends(database.get_db)
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")

        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Додавання завдання тільки для гравця з id = 1
        if user.id == 1:
            TaskHelper.create_task(db, title, description, level_required, reward_gold, reward_wood, reward_stone, reward_exp)
        else:
            raise HTTPException(status_code=403, detail="Permission denied")

        return RedirectResponse(url="/char_tasks", status_code=303)

    @router.post("/complete-task/{task_id}")
    async def complete_task(
        task_id: int,
        db: Session = Depends(database.get_db),
        current_user: models.User = Depends(database.get_current_user)
    ):
        if not current_user:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        # Отримуємо завдання користувача
        user_task = db.query(models.UserTask).filter(
            models.UserTask.user_id == current_user.id,
            models.UserTask.task_id == task_id,
            models.UserTask.is_completed == False
        ).first()
        
        if not user_task:
            raise HTTPException(status_code=404, detail="Task not found or already completed")
        
        # Виконуємо завдання та видаємо нагороду
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        user_task.is_completed = True
        current_user.gold += task.reward_gold
        current_user.wood += task.reward_wood
        current_user.stone += task.reward_stone
        current_user.experience += task.reward_exp
        
        db.commit()
        
        # Якщо це перше завдання, даємо досягнення
        if task_id == 1:
            # Перевіряємо чи немає вже цього досягнення
            existing_achievement = db.query(models.UserAchievement).filter(
                models.UserAchievement.user_id == current_user.id,
                models.UserAchievement.achievement_id == 1
            ).first()
            
            if not existing_achievement:
                user_achievement = models.UserAchievement(
                    user_id=current_user.id,
                    achievement_id=1
                )
                db.add(user_achievement)
                db.commit()
        
        return RedirectResponse(url="/char_tasks", status_code=303)