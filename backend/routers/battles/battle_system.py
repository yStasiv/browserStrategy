# --- Conceptual Python Backend using FastAPI ---
# NOTE: This code requires FastAPI and Uvicorn (`pip install fastapi uvicorn python-multipart fastapi-cors`)
# and needs to be run locally using `uvicorn main:app --reload` (assuming the file is named main.py).
# It cannot run directly in this environment.

import random
from fastapi import FastAPI, HTTPException, Body
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel # Для валідації даних запиту
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from ... import models

# --- Game Constants ---
GRID_WIDTH = 10
GRID_HEIGHT = 8
DEPLOYMENT_COLUMNS = 3
AI_PLAYER_NUMBER = 2

# --- Creature Types Data ---
creature_types_data = {
    'knight': {'name': 'knight', 'emoji': '♘', 'maxHp': 20, 'attack': 5, 'movement': 3, 'range': 1},
    'archer': {'name': 'archer', 'emoji': '🏹', 'maxHp': 12, 'attack': 4, 'movement': 2, 'range': 4},
    'skeleton': {'name': 'skeleton', 'emoji': '💀', 'maxHp': 15, 'attack': 3, 'movement': 2, 'range': 1},
    'goblin': {'name': 'goblin', 'emoji': '👺', 'maxHp': 10, 'attack': 2, 'movement': 4, 'range': 1},
}

initial_army_data = { 'knight': 1, 'archer': 1, 'goblin': 1 }

# --- Helper Functions ---
def generate_id():
    return ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=7))

def calculate_distance(x1, y1, x2, y2):
    return abs(x1 - x2) + abs(y1 - y2)

# --- Game Classes (залишаються такими ж) ---
class Creature:
    def __init__(self, type_name, player, x, y):
        type_data = creature_types_data.get(type_name)
        if not type_data:
            raise ValueError(f"Unknown creature type: {type_name}")
        self.id = generate_id()
        self.type = type_data
        self.player = player
        self.x = x
        self.y = y
        self.hp = type_data['maxHp']
        self.can_move = False
        self.can_attack = False
        self.retaliated_this_turn = False

    def to_dict(self):
        return {
            'id': self.id,
            'type_name': self.type['name'],
            'emoji': self.type['emoji'],
            'player': self.player,
            'x': self.x,
            'y': self.y,
            'hp': self.hp,
            'maxHp': self.type['maxHp'],
            'canMove': self.can_move,
            'canAttack': self.can_attack,
        }

class BattleSystem:
    def __init__(self, user: models.User, db: Optional[Session] = None):
        self.user = user
        self.db = db
        # self.enemies: list[models.Enemy] = []
        self.game_state = 'mode_selection'
        self.game_mode = 'pve'
        self.current_player = 1
        self.deployment_player = 1
        self.creatures = {} # {id: Creature_object}
        self.player1_deployment_pool = {}
        self.player2_deployment_pool = {}
        self.message = "Виберіть режим гри"
        print("Game instance created.") # Лог при створенні гри

    def start_game(self, mode):
        print(f"Starting game in mode: {mode}")
        self.game_mode = mode
        self.game_state = 'deployment'
        self.current_player = 1
        self.deployment_player = 1
        self.creatures = {}
        self.player1_deployment_pool = initial_army_data.copy()
        self.player2_deployment_pool = initial_army_data.copy()
        self.message = f"Розстановка: Гравець 1"
        return self.get_state()

    def get_creature_at(self, x, y):
        for creature in self.creatures.values():
            if creature.x == x and creature.y == y:
                return creature
        return None

    def is_in_deployment_zone(self, x, y, player):
        start_col = 0 if player == 1 else GRID_WIDTH - DEPLOYMENT_COLUMNS
        end_col = start_col + DEPLOYMENT_COLUMNS
        return start_col <= x < end_col and 0 <= y < GRID_HEIGHT

    def place_creature(self, player, type_name, x, y):
        if self.game_state != 'deployment' or player != self.deployment_player:
            self.message = "Зараз не ваша черга розставляти!"
            return False, self.message

        pool = self.player1_deployment_pool if player == 1 else self.player2_deployment_pool

        if not self.is_in_deployment_zone(x, y, player):
            self.message = "Не можна розмістити тут!"
            return False, self.message
        if self.get_creature_at(x, y):
            self.message = "Клітинка зайнята!"
            return False, self.message
        if pool.get(type_name, 0) <= 0:
            self.message = f"Немає більше {type_name} для розстановки."
            return False, self.message

        try:
            new_creature = Creature(type_name, player, x, y)
            self.creatures[new_creature.id] = new_creature
            pool[type_name] -= 1
            self.message = f"Гравець {player} розмістив {type_name}."
            print(f"Placed {type_name} for P{player} at ({x},{y}). Pool: {pool}")

            if all(count == 0 for count in pool.values()):
                self.advance_deployment()

            return True, self.message
        except ValueError as e:
            self.message = str(e)
            return False, self.message

    def advance_deployment(self):
        print(f"Advancing deployment from player {self.deployment_player}")
        if self.deployment_player == 1:
            if self.game_mode == 'pvp':
                self.deployment_player = 2
                self.message = "Розстановка: Гравець 2"
            else: # PvE
                self.deploy_ai_creatures()
                self.start_battle()
        else: # Player 2 (PvP) finished
            self.start_battle()

    def deploy_ai_creatures(self):
        print("AI deploying...")
        player = AI_PLAYER_NUMBER
        pool = self.player2_deployment_pool
        start_col = GRID_WIDTH - DEPLOYMENT_COLUMNS
        end_col = GRID_WIDTH
        available_cells = []
        for y in range(GRID_HEIGHT):
            for x in range(start_col, end_col):
                if not self.get_creature_at(x, y):
                    available_cells.append({'x': x, 'y': y})

        for type_name, count in pool.items():
            for _ in range(count):
                if not available_cells:
                    print(f"ERROR: No space left for AI to deploy {type_name}")
                    break
                cell_index = random.randrange(len(available_cells))
                cell = available_cells.pop(cell_index)
                try:
                    new_creature = Creature(type_name, player, cell['x'], cell['y'])
                    self.creatures[new_creature.id] = new_creature
                    print(f"AI placed {type_name} at ({cell['x']},{cell['y']})")
                except ValueError as e:
                    print(f"Error creating AI creature: {e}")
            pool[type_name] = 0

    def start_battle(self):
        print("Starting battle")
        self.game_state = 'battle'
        self.current_player = 1
        self.message = "Бій розпочато! Хід Гравця 1."
        for creature in self.creatures.values():
            creature.retaliated_this_turn = False
            if creature.player == self.current_player:
                creature.can_move = True
                creature.can_attack = True
            else:
                creature.can_move = False
                creature.can_attack = False

    def move_creature(self, creature_id, target_x, target_y):
        if self.game_state != 'battle': return False, "Зараз не бій"
        creature = self.creatures.get(creature_id)
        if not creature or creature.player != self.current_player: return False, "Не ваше створіння"
        if not creature.can_move: return False, "Вже рухався"

        distance = calculate_distance(creature.x, creature.y, target_x, target_y)
        if distance == 0 or distance > creature.type['movement']: return False, "Неправильна відстань"
        if self.get_creature_at(target_x, target_y): return False, "Клітинка зайнята"

        # Зберігаємо старі координати для логування
        old_x, old_y = creature.x, creature.y
        
        creature.x = target_x
        creature.y = target_y
        creature.can_move = False
        self.message = f"{creature.type['emoji']} перемістився з ({old_x}, {old_y}) на ({target_x}, {target_y})."
        print(f"Creature {creature.type['name']} moved from ({old_x}, {old_y}) to ({target_x}, {target_y})")
        return True, self.message

    def attack_creature(self, attacker_id, defender_id):
        if self.game_state != 'battle': return False, "Зараз не бій"
        attacker = self.creatures.get(attacker_id)
        defender = self.creatures.get(defender_id)

        if not attacker or attacker.player != self.current_player: return False, "Не ваше створіння для атаки"
        if not defender or defender.player == self.current_player: return False, "Не можна атакувати своїх"
        if not attacker.can_attack: return False, "Вже атакував"

        distance = calculate_distance(attacker.x, attacker.y, defender.x, defender.y)
        if distance > attacker.type['range']: return False, "Ціль занадто далеко"

        damage = attacker.type['attack']
        defender.hp -= damage
        attacker.can_attack = False
        if attacker.type['name'] != 'knight': attacker.can_move = False
        self.message = f"{attacker.type['emoji']} атакував {defender.type['emoji']} на {damage} шкоди."
        print(f"Attack: {attacker.id} -> {defender.id}. Defender HP: {defender.hp}")

        defender_defeated = False
        attacker_defeated = False

        if defender.hp > 0 and not defender.retaliated_this_turn:
             retaliation_distance = calculate_distance(defender.x, defender.y, attacker.x, attacker.y)
             if retaliation_distance <= defender.type['range']:
                 retaliation_damage = defender.type['attack']
                 attacker.hp -= retaliation_damage
                 defender.retaliated_this_turn = True
                 self.message += f" {defender.type['emoji']} контратакував на {retaliation_damage} шкоди."
                 print(f"Retaliation: {defender.id} -> {attacker.id}. Attacker HP: {attacker.hp}")
                 if attacker.hp <= 0:
                     attacker_defeated = True

        if defender.hp <= 0:
            self.message += f" {defender.type['emoji']} переможено!"
            defender_defeated = True

        if defender_defeated:
             # Перевіряємо існування перед видаленням
             if defender_id in self.creatures:
                 del self.creatures[defender_id]
                 print(f"Defender {defender_id} defeated and removed.")
             else:
                 print(f"Attempted to remove already removed defender {defender_id}")
        if attacker_defeated:
             self.message += f" {attacker.type['emoji']} переможено контратакою!"
              # Перевіряємо існування перед видаленням
             if attacker_id in self.creatures:
                 del self.creatures[attacker_id]
                 print(f"Attacker {attacker_id} defeated by retaliation and removed.")
             else:
                  print(f"Attempted to remove already removed attacker {attacker_id}")


        if self.check_win_condition()[0]:
             return True, self.message

        return True, self.message


    def end_turn(self):
        if self.game_state != 'battle': return False, "Зараз не бій"
        if self.current_player != 1: return False, "Не ваша черга"

        # Перевіряємо умови перемоги перед зміною гравця
        win_check = self.check_win_condition()
        if win_check[0]: return True, win_check[1]

        print("Ending player turn, switching to AI")
        self.current_player = 2
        self.message = "Хід ШІ."

        # Оновлюємо можливості створінь для ШІ
        for creature in self.creatures.values():
            creature.retaliated_this_turn = False
            if creature.player == self.current_player:
                creature.can_move = True
                creature.can_attack = True
            else:
                creature.can_move = False
                creature.can_attack = False

        # Якщо це PvE і хід ШІ, виконуємо хід ШІ
        if self.game_mode == 'pve':
            print("Executing AI turn")
            self.execute_ai_turn()
            print("AI turn completed")

        return True, self.message

    def execute_ai_turn(self):
        print("AI turn started")
        ai_creatures = [c for c in self.creatures.values() if c.player == AI_PLAYER_NUMBER]
        
        for creature in ai_creatures:
            print(f"Processing AI creature {creature.type['name']} at ({creature.x}, {creature.y})")
            # Знаходимо найближчу ворожу ціль
            enemy_creatures = [c for c in self.creatures.values() if c.player != AI_PLAYER_NUMBER]
            if not enemy_creatures:
                print("No enemy creatures found")
                continue

            # Знаходимо найближчу ціль
            closest_enemy = min(enemy_creatures, 
                              key=lambda e: calculate_distance(creature.x, creature.y, e.x, e.y))
            print(f"Closest enemy is {closest_enemy.type['name']} at ({closest_enemy.x}, {closest_enemy.y})")
            
            # Перевіряємо чи можемо атакувати
            if creature.can_attack:
                distance = calculate_distance(creature.x, creature.y, closest_enemy.x, closest_enemy.y)
                print(f"Distance to enemy: {distance}, attack range: {creature.type['range']}")
                if distance <= creature.type['range']:
                    # Атакуємо
                    success, message = self.attack_creature(creature.id, closest_enemy.id)
                    print(f"AI attack: {message}")
                    if success:
                        # Перевіряємо чи гра закінчена
                        win_check = self.check_win_condition()
                        if win_check[0]:
                            return
                    continue

            # Якщо не можемо атакувати, намагаємось наблизитися
            if creature.can_move:
                print(f"Trying to move {creature.type['name']} closer to enemy")
                # Знаходимо найкращу позицію для руху
                best_move = None
                best_distance = float('inf')
                
                # Перевіряємо всі можливі клітинки в радіусі руху
                for dx in range(-creature.type['movement'], creature.type['movement'] + 1):
                    for dy in range(-creature.type['movement'], creature.type['movement'] + 1):
                        # Перевіряємо чи сума руху не перевищує максимальну дистанцію
                        if abs(dx) + abs(dy) > creature.type['movement']:
                            continue
                            
                        new_x = creature.x + dx
                        new_y = creature.y + dy
                        
                        # Перевіряємо чи клітинка в межах поля і вільна
                        if (0 <= new_x < GRID_WIDTH and 
                            0 <= new_y < GRID_HEIGHT and 
                            not self.get_creature_at(new_x, new_y)):
                            
                            # Перевіряємо чи це покращує нашу позицію
                            new_distance = calculate_distance(new_x, new_y, closest_enemy.x, closest_enemy.y)
                            if new_distance < best_distance:
                                best_distance = new_distance
                                best_move = (new_x, new_y)
                                print(f"Found better move: ({new_x}, {new_y}) with distance {new_distance}")
                
                # Якщо знайшли хороший хід, рухаємось
                if best_move:
                    print(f"Moving to {best_move}")
                    success, message = self.move_creature(creature.id, best_move[0], best_move[1])
                    print(f"AI move: {message}")
                    
                    # Після руху перевіряємо чи можемо атакувати
                    if success and creature.can_attack:
                        distance = calculate_distance(creature.x, creature.y, closest_enemy.x, closest_enemy.y)
                        print(f"After move - Distance to enemy: {distance}, attack range: {creature.type['range']}")
                        if distance <= creature.type['range']:
                            success, message = self.attack_creature(creature.id, closest_enemy.id)
                            print(f"AI attack after move: {message}")
                            if success:
                                # Перевіряємо чи гра закінчена
                                win_check = self.check_win_condition()
                                if win_check[0]:
                                    return
                else:
                    print(f"No valid move found for {creature.type['name']}")

        # Перевіряємо умови перемоги після ходу ШІ
        win_check = self.check_win_condition()
        if not win_check[0]:
            # Якщо гра продовжується, повертаємо хід гравцю
            self.current_player = 1
            self.message = "Хід Гравця 1."
            # Оновлюємо можливості створінь для гравця
            for creature in self.creatures.values():
                creature.retaliated_this_turn = False
                if creature.player == self.current_player:
                    creature.can_move = True
                    creature.can_attack = True
                else:
                    creature.can_move = False
                    creature.can_attack = False

    def check_win_condition(self):
        player1_creatures = any(c.player == 1 and c.hp > 0 for c in self.creatures.values())
        player2_creatures = any(c.player == AI_PLAYER_NUMBER and c.hp > 0 for c in self.creatures.values())

        # Перевіряємо, чи взагалі є створіння у грі
        if not player1_creatures and not player2_creatures and self.game_state == 'battle':
             # Можливо, нічия або помилка, якщо бій почався без створінь
             self.game_state = 'game_over'
             self.message = "Гру завершено (немає створінь)."
             print("Game Over: No creatures left.")
             return True, self.message

        if not player1_creatures and player2_creatures:
            self.game_state = 'game_over'
            self.message = f"{self.get_player_name(AI_PLAYER_NUMBER)} переміг!"
            print("Game Over:", self.message)
            return True, self.message
        elif not player2_creatures and player1_creatures:
            self.game_state = 'game_over'
            self.message = f"{self.get_player_name(1)} переміг!"
            print("Game Over:", self.message)
            return True, self.message
        return False, ""

    def get_player_name(self, player_number):
        if self.game_mode == 'pve' and player_number == AI_PLAYER_NUMBER:
            return "ШІ"
        return f"Гравець {player_number}"

    def get_state(self):
        return {
            'gameState': self.game_state,
            'gameMode': self.game_mode,
            'currentPlayer': self.current_player,
            'deploymentPlayer': self.deployment_player,
            'creatures': [c.to_dict() for c in self.creatures.values()],
            'player1DeploymentPool': self.player1_deployment_pool,
            'player2DeploymentPool': self.player2_deployment_pool,
            'message': self.message,
        }

# --- FastAPI App Setup ---
# app = FastAPI()

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

# # Налаштування CORS
# origins = [
#     "http://localhost", # Якщо запускаєте HTML локально
#     "http://127.0.0.1",
#     "null", # Для локальних файлів (відкритих через file://)
#     # Додайте сюди інші джерела, якщо потрібно
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"], # Дозволити всі методи (GET, POST, etc.)
#     allow_headers=["*"], # Дозволити всі заголовки
# )

# --- Глобальний об'єкт гри ---
# Створюємо екземпляр гри при старті сервера

game: BattleSystem = BattleSystem(user = "")

# --- Pydantic Models for Request Validation ---
class StartGameRequest(BaseModel):
    mode: Optional[str] = 'pve'

class DeployRequest(BaseModel):
    player: int
    typeName: str
    x: int
    y: int

class MoveRequest(BaseModel):
    creatureId: str
    targetX: int
    targetY: int

class AttackRequest(BaseModel):
    attackerId: str
    defenderId: str

# --- API Endpoints ---

@router.post("/start")
async def start_new_game(request_data: StartGameRequest):
    # Використовуємо глобальний об'єкт game
    state = game.start_game(request_data.mode)
    return state # FastAPI автоматично конвертує dict в JSON

@router.get("/state")
async def get_game_state():
    return game.get_state()

@router.post("/deploy")
async def deploy_creature(request_data: DeployRequest):
    # Використовуємо дані з Pydantic моделі
    success, message = game.place_creature(
        request_data.player,
        request_data.typeName,
        request_data.x,
        request_data.y
    )
    response = game.get_state()
    response['actionSuccess'] = success
    if not success:
         # Можна повернути помилку, якщо дія не вдалася
         # raise HTTPException(status_code=400, detail=message)
         # Або просто передати повідомлення через стан гри
         pass
    return response

@router.post("/move")
async def move_creature_api(request_data: MoveRequest):
    success, message = game.move_creature(
        request_data.creatureId,
        request_data.targetX,
        request_data.targetY
    )
    response = game.get_state()
    response['actionSuccess'] = success
    if not success:
        # raise HTTPException(status_code=400, detail=message)
        pass
    return response

@router.post("/attack")
async def attack_creature_api(request_data: AttackRequest):
    success, message = game.attack_creature(
        request_data.attackerId,
        request_data.defenderId
    )
    response = game.get_state()
    response['actionSuccess'] = success
    if not success:
       # raise HTTPException(status_code=400, detail=message)
       pass
    return response

@router.post("/end_turn")
async def end_turn_api():
    success, message = game.end_turn()
    response = game.get_state()
    response['actionSuccess'] = success
    if not success:
        # raise HTTPException(status_code=400, detail=message)
        pass
    return response

# --- Запуск сервера (для локального тестування) ---
# Запускати через: uvicorn main:app --reload --port 5000
# (де main - ім'я вашого python файлу)
# if __name__ == "__main__":
#     import uvicorn
#     # Запуск Uvicorn програмно (альтернатива командному рядку)
#     # Зазвичай краще запускати з командного рядка
#     uvicorn.run(router, host="127.0.0.1", port=5000)

