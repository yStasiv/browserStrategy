from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
import json
import os
from typing import Dict, List
from ... import models, database
from ...auth import get_current_user
from fastapi.templating import Jinja2Templates
from .battle_system import BattleSystem

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

# Словник для зберігання активних битв
active_battles = {}

@router.get("/battle")
async def battle_page(request: Request, db: Session = Depends(database.get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Створюємо нову битву для користувача
    battle_system: BattleSystem = BattleSystem(user=user, db=db)
    active_battles[user.id] = battle_system
    
    return templates.TemplateResponse(
        "battle.html",
        {
            "request": request,
            "player": user,
            "battle_state": battle_system.get_battle_state()
        }
    )

@router.post("/battle/action")
async def battle_action(
    request: Request,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Отримуємо дані з тіла запиту
    data = await request.json()
    action = data.get("action")
    direction = data.get("direction")
    
    if not action:
        raise HTTPException(status_code=400, detail="Action is required")
    
    # Отримуємо активну битву користувача
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")

    
    # Виконуємо дію відповідно до запиту
    if action == "move":
        if not direction:
            raise HTTPException(status_code=400, detail="Direction is required for move action")
        result = battle_system.move(direction)
    elif action == "attack":
        result = battle_system.attack()
    elif action == "defend":
        result = battle_system.defend()
    elif action == "special_attack":
        result = battle_system.special_attack()
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    # Перевіряємо, чи є помилка в результаті
    if result["error"] is not None:
        raise HTTPException(status_code=400, detail=result["error"])
    
    # Логіка для ворога


    # if not result["winner"] and battle_system.enemy_moves > 0:
    #     enemy_result = battle_system.enemy_decision()
    #     if enemy_result["error"]:
    #         raise HTTPException(status_code=400, detail=enemy_result["error"])
        
    # Якщо битва закінчена, видаляємо її з активних
    if result["winner"]:
        del active_battles[user.id]

    

    
    return result

@router.get("/battle/state")
async def battle_state(request: Request, db: Session = Depends(database.get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Отримуємо активну битву користувача
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")
    
    return battle_system.get_battle_state()

@router.post("/battle/save-turn")
async def save_battle_turn(
    turn_data: Dict,
    request: Request,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Створюємо директорію для збереження бойових логів, якщо вона не існує
    battle_logs_dir = "battle_logs"
    if not os.path.exists(battle_logs_dir):
        os.makedirs(battle_logs_dir)
    
    # Формуємо ім'я файлу
    current_time = datetime.now()
    filename = f"{current_time.strftime('%y-%m-%d:%H-%M')}-{user.username}-{turn_data.get('enemy_name', 'unknown')}.json"
    file_path = os.path.join(battle_logs_dir, filename)
    
    # Зберігаємо дані ходу
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(turn_data, f, ensure_ascii=False, indent=2)
    
    return {"message": "Battle turn saved successfully", "filename": filename} 