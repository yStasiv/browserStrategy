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
    battle_system = BattleSystem(user=user, db=db)
    active_battles[user.id] = battle_system
    
    return templates.TemplateResponse(
        "battle.html",
        {
            "request": request,
            "player": user,
            "battle_state": battle_system.get_state()
        }
    )

@router.post("/battle/start")
async def start_battle(
    mode: str = "pve",
    request: Request = None,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    battle_system = active_battles.get(user.id)
    if not battle_system:
        battle_system = BattleSystem(user=user, db=db)
        active_battles[user.id] = battle_system
    else:
        # Оновлюємо сесію бази даних для існуючого екземпляра
        battle_system.db = db
    
    state = battle_system.start_game(mode)
    return state

@router.post("/battle/deploy")
async def deploy_creature(
    player: int,
    type_name: str,
    x: int,
    y: int,
    request: Request = None,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")
    
    success, message = battle_system.place_creature(player, type_name, x, y)
    return battle_system.get_state()

@router.post("/battle/move")
async def move_creature(
    creature_id: str,
    target_x: int,
    target_y: int,
    request: Request = None,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")
    
    success, message = battle_system.move_creature(creature_id, target_x, target_y)
    return battle_system.get_state()

@router.post("/battle/attack")
async def attack_creature(
    attacker_id: str,
    defender_id: str,
    request: Request = None,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")
    
    success, message = battle_system.attack_creature(attacker_id, defender_id)
    
    # Якщо бій закінчено і гравець переміг, надаємо винагороду
    if battle_system.game_state == 'game_over' and "Гравець 1 переміг!" in message:
        # Надаємо винагороду гравцю
        user.gold += 100  # Наприклад, 100 золота
        user.experience += 50  # Наприклад, 50 досвіду
        db.commit()
        message += f" Ви отримали винагороду: 100 золота та 50 досвіду!"
    
    return battle_system.get_state()

@router.post("/battle/end_turn")
async def end_turn_api(request: Request = None, db: Session = Depends(database.get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")
    
    # Оновлюємо сесію бази даних
    battle_system.db = db
    
    success, message = battle_system.end_turn()
    response = battle_system.get_state()
    response['actionSuccess'] = success
    if not success:
        pass
    return response

@router.get("/battle/state")
async def get_battle_state(
    request: Request = None,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    battle_system = active_battles.get(user.id)
    if not battle_system:
        raise HTTPException(status_code=404, detail="No active battle found")
    
    # Оновлюємо сесію бази даних
    battle_system.db = db
    
    return battle_system.get_state()

@router.get("/battle/rating")
async def get_player_rating(
    request: Request = None,
    db: Session = Depends(database.get_db)
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Отримуємо рейтинг гравця
    player_rating = db.query(models.PlayerRating).filter(
        models.PlayerRating.user_id == user.id
    ).first()
    
    if not player_rating:
        # Якщо рейтингу ще немає, створюємо новий
        player_rating = models.PlayerRating(user_id=user.id)
        db.add(player_rating)
        db.commit()
        db.refresh(player_rating)
    
    return {
        "rating": player_rating.rating,
        "wins": player_rating.wins,
        "losses": player_rating.losses
    }

# @router.post("/battle/save-turn")
# async def save_battle_turn(
#     turn_data: Dict,
#     request: Request,
#     db: Session = Depends(database.get_db)
# ):
#     user = await get_current_user(request, db)
#     if not user:
#         raise HTTPException(status_code=401, detail="Not authenticated")
    
#     # Створюємо директорію для збереження бойових логів, якщо вона не існує
#     battle_logs_dir = "battle_logs"
#     if not os.path.exists(battle_logs_dir):
#         os.makedirs(battle_logs_dir)
    
#     # Формуємо ім'я файлу
#     current_time = datetime.now()
#     filename = f"{current_time.strftime('%y-%m-%d:%H-%M')}-{user.username}-{turn_data.get('enemy_name', 'unknown')}.json"
#     file_path = os.path.join(battle_logs_dir, filename)
    
#     # Зберігаємо дані ходу
#     with open(file_path, 'w', encoding='utf-8') as f:
#         json.dump(turn_data, f, ensure_ascii=False, indent=2)
    
#     return {"message": "Battle turn saved successfully", "filename": filename} 