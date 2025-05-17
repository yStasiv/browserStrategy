from datetime import datetime
import json
import os
from sqlalchemy.orm import Session
from typing import Dict, Any, Union, Optional
from ... import models

class BattleSystem:
    def __init__(self, user: models.User, db: Optional[Session] = None):
        self.user = user
        self.db = db
        self.enemies: list[models.Enemy] = []

        
        # Ініціалізуємо стан битви
        if db:
            self.battle_state = models.BattleState(
                user_id=user.id,
                enemy_id=self.enemy.id,
                player_position={"x": 0, "y": 0},
                enemy_position={"x": 19, "y": 9},
                player_hp=100,
                enemy_hp=self.enemy.hp,
                turn=1,
                player_moves=2,
                enemy_moves=2,
                battle_ended=False,
                winner=None
            )
            db.add(self.battle_state)
            db.commit()
            db.refresh(self.battle_state)
        else:
            self.battle_state = {
                "player_position": {"x": 0, "y": 0},
                "enemy_position": {"x": 19, "y": 9},
                "player_hp": 100,
                "enemy_hp": self.enemy.hp,
                "turn": 1,
                "player_moves": 3,
                "enemy_moves": 2,
                "battle_ended": False,
                "winner": None
            }
    
    def _create_enemy(self) -> Union[models.Enemy, Dict[str, Any]]:
        """Створює ворога для битви"""
        if self.db:
            if not self.enemies:
                # Тут можна додати логіку вибору ворога з бази даних
                enemy = models.Enemy(
                    name="Тестовий ворог",
                    level=1,
                    hp=100,
                    melee_attack=10,
                    physical_defense=5,
                    enemy_moves=2,
                    magic_power=5,
                    magic_resistance=5
                )
                self.db.add(enemy)
                self.db.commit()
                self.db.refresh(enemy)
                return enemy
            else:
                return {
                    "name": "Тестовий ворог",
                    "level": 1,
                    "hp": 100,
                    "melee_attack": 10,
                    "physical_defense": 5,
                    "magic_power": 5,
                    "magic_resistance": 5
                }
    
    def get_battle_state(self) -> Dict[str, Any]:
        """Повертає поточний стан битви"""
        if self.db:
            return {
                "player_hp": self.battle_state.player_hp,
                "enemy_hp": self.battle_state.enemy_hp,
                "battle_ended": self.battle_state.battle_ended,
                "winner": self.battle_state.winner,
                "player_moves": self.battle_state.player_moves,
                "enemy_moves": self.battle_state.enemy_moves,
                "player_position": self.battle_state.player_position,
                "enemy_position": self.battle_state.enemy_position
            }
        else:
            return self.battle_state
    
    def move(self, direction: str) -> Dict[str, Any]:
        """Переміщення гравця"""
        if self.battle_state.winner:
            return {"error": "Битва вже закінчена"}
        
        if self.battle_state.player_moves <= 0:
            return {"error": "Закінчились ходи для руху"}
        
        new_position = self.battle_state.player_position.copy()
        
        if direction == "up":
            new_position["y"] = max(0, new_position["y"] - 1)
        elif direction == "down":
            new_position["y"] = min(9, new_position["y"] + 1)
        elif direction == "left":
            new_position["x"] = max(0, new_position["x"] - 1)
        elif direction == "right":
            new_position["x"] = min(19, new_position["x"] + 1)
        else:
            return {"error": "Невідомий напрямок руху"}
        
        # Перевіряємо, чи не зайнята клітинка ворогом
        if (new_position["x"] == self.battle_state.enemy_position["x"] and 
            new_position["y"] == self.battle_state.enemy_position["y"]):
            return {"error": "Ця клітинка зайнята ворогом"}
        
        self.battle_state.player_position = new_position
        self.battle_state.player_moves -= 1
        
        # Зберігаємо стан в базу даних
        if self.db:
            self.db.commit()
        
        print(self._create_battle_response())
        return self._create_battle_response()
        
    
    def attack(self) -> Dict[str, Any]:
        """Атака гравця"""
        if self.battle_state.winner:
            return {"error": "Битва вже закінчена"}
        
        # Перевіряємо дистанцію до ворога
        distance = self._calculate_distance(
            self.battle_state.player_position,
            self.battle_state.enemy_position
        )
        
        if distance > 1:
            return {"error": "Ворог занадто далеко для атаки"}
        
        # Розраховуємо пошкодження
        damage = self._calculate_damage(
            self.user.melee_attack,
            self.enemy.physical_defense if isinstance(self.enemy, models.Enemy) else self.enemy["physical_defense"]
        )
        
        self.battle_state.enemy_hp -= damage
        
        # Перевіряємо чи битва закінчена
        self._check_battle_end()
        
        # Зберігаємо стан в базу даних
        if self.db:
            self.db.commit()
        
        return self._create_battle_response()
    
    def defend(self) -> Dict[str, Any]:
        """Захист гравця"""
        if self.battle_state.winner:
            return {"error": "Битва вже закінчена"}
        
        # Зберігаємо стан в базу даних
        if self.db:
            self.db.commit()
        
        return self._create_battle_response()
    
    def special_attack(self) -> Dict[str, Any]:
        """Спеціальна атака гравця"""
        if self.battle_state.winner:
            return {"error": "Битва вже закінчена"}
        
        # Перевіряємо дистанцію до ворога
        distance = self._calculate_distance(
            self.battle_state.player_position,
            self.battle_state.enemy_position
        )
        
        if distance > 2:
            return {"error": "Ворог занадто далеко для спеціальної атаки"}
        
        # Розраховуємо пошкодження
        damage = self._calculate_damage(
            self.user.magic_power,
            self.enemy.magic_resistance if isinstance(self.enemy, models.Enemy) else self.enemy["magic_resistance"]
        )
        
        self.battle_state.enemy_hp -= damage
        
        # Перевіряємо чи битва закінчена
        self._check_battle_end()
        
        # Зберігаємо стан в базу даних
        if self.db:
            self.db.commit()
        
        return self._create_battle_response()
    
    def _calculate_distance(self, pos1: Dict[str, int], pos2: Dict[str, int]) -> int:
        """Розраховує відстань між двома точками"""
        return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])
    
    def _calculate_damage(self, attack: int, defense: int) -> int:
        """Розраховує пошкодження"""
        base_damage = max(1, attack - defense)
        return base_damage
    
    def _check_battle_end(self) -> None:
        """Перевіряє чи битва закінчена"""
        if self.battle_state.player_hp <= 0:
            self.battle_state.battle_ended = True
            self.battle_state.winner = "enemy"
        elif self.battle_state.enemy_hp <= 0:
            self.battle_state.battle_ended = True
            self.battle_state.winner = "player"
    
    def _create_battle_response(self) -> Dict[str, Any]:
        """Створює відповідь з поточним станом битви"""
        return {
            "player_hp": self.battle_state.player_hp,
            "enemy_hp": self.battle_state.enemy_hp,
            "battle_ended": self.battle_state.battle_ended,
            "winner": self.battle_state.winner,
            "enemy_position": self.battle_state.enemy_position,
            "player_position":self.battle_state.player_position, 
            "player_moves": self.battle_state.player_moves, 
            "error": None
        } 
    
    def enemy_decision(self):
        """Розрахунок дії ворога залежно від стану гри."""
        if self.battle_state.enemy_hp < 20 and self.battle_state.player_hp > self.enemy_hp:
            return self.defend()  # Захищається при низькому HP
        elif self.is_player_nearby():
            return self.attack()  # Атакує, якщо гравець поруч
        else:
            return self.move_towards_player()  # Наближається до гравця

    def is_player_nearby(self):
        """Перевіряє, чи знаходиться гравець поруч із ворогом."""
        enemy_x, enemy_y = self.battle_state.enemy_position['x'], self.battle_state.enemy_position['y']
        player_x, player_y = self.battle_state.player_position['x'], self.battle_state.player_position['y']
        return abs(enemy_x - player_x) <= 1 and abs(enemy_y - player_y) <= 1

    def move_towards_player(self):
        """Вибирає напрямок руху до гравця."""
        if self.battle_state.enemy_position['x'] < self.battle_state.player_position['x']:
            return self.move("right")
        elif self.battle_state.enemy_position['x'] > self.battle_state.player_position['x']:
            return self.move("left")
        elif self.battle_state.enemy_position['y'] < self.battle_state.player_position['y']:
            return self.move("down")
        elif self.battle_state.enemy_position['y'] > self.battle_state.player_position['y']:
            return self.move("up")