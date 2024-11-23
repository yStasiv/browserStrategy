from fastapi import APIRouter, HTTPException, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from backend import models, database

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

class TaskHelper:
    @staticmethod
    def update_tasks_for_users(db: Session, db_task: models.Task, all_users: list[models.User]) -> None:
         # Add this task for each users
        # users = db.query(models.User).all() 
        # all_created_taks = TaskHelper.get_tasks(db, 1)
        # for task in all_created_taks:
        for user in all_users: 
            user_task = models.UserTask(user_id=user.id, task_id=db_task.id) 
            db.add(user_task) 
        db.commit()

    @staticmethod
    def create_task(db: Session, title: str, description: str, level_required: int) -> models.Task:
        db_task = models.Task(title=title, description=description, level_required=level_required)       
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
    def get_user_tasks(db: Session, user: models.User): 
        tasks = db.query(models.UserTask).join(models.Task).filter( models.UserTask.user_id == user.id, models.Task.level_required <= user.level ).all()
        if user.id == 1:
            tasks = db.query(models.UserTask).join(models.Task).filter( models.UserTask.user_id == user.id).all()
        return tasks
        # return db.query(models.UserTask).filter(models.UserTask.user_id == user_id).all()
    
    @staticmethod 
    def update_task_completion(db: Session, user_id: int, task_id: int, is_completed: bool): 
        user_task = db.query(models.UserTask).filter(models.UserTask.user_id == user_id, models.UserTask.task_id == task_id ).first() 
        if user_task: 
            user_task.is_completed = is_completed 
            db.commit() 
            return user_task 
        else: 
            raise HTTPException(status_code=404, detail="User task not found")
    

class TaskRoutes(TaskHelper):
    @router.get("/char_tasks", response_class=HTMLResponse)
    async def get_tasks_page(
        request: Request,
        db: Session = Depends(database.get_db)
    ):
        user_session_id = request.cookies.get("session_id")
        if not user_session_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        tasks = TaskHelper.get_all_tasks(db)
        user_tasks = TaskHelper.get_user_tasks(db, user)

        return templates.TemplateResponse("char_tasks.html", {"request": request, "user": user, "user_tasks": user_tasks})

    @router.post("/char_tasks/add", response_class=RedirectResponse)
    async def add_task(
        request: Request,
        title: str = Form(...),
        description: str = Form(...),
        level_required: int = Form(...),
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
            TaskHelper.create_task(db, title, description, level_required)
        else:
            raise HTTPException(status_code=403, detail="Permission denied")

        return RedirectResponse(url="/char_tasks", status_code=303)

    @router.post("/char_tasks/complete", response_class=RedirectResponse) 
    async def complete_task( 
            request: Request, 
            task_id: int = Form(...), 
            db: Session = Depends(database.get_db) 
        ): 
        user_session_id = request.cookies.get("session_id") 
        if not user_session_id: 
            raise HTTPException(status_code=401, detail="Not logged in") 
        user = db.query(models.User).filter(models.User.session_id == user_session_id).first() 
        if not user: 
            raise HTTPException(status_code=404, detail="User not found") 
        TaskHelper.update_task_completion(db, user.id, task_id, True) 
        return RedirectResponse(url="/char_tasks", status_code=303)