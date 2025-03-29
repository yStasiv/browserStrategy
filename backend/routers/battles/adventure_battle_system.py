from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import random
from datetime import datetime

app = FastAPI()


class Character(BaseModel):
    name: str
    stamina: int
    energy: int
    agility: int
    mind: int
    melee_attack_bonus: int = 0
    ranged_attack_bonus: int = 0
    physical_defense_bonus: int = 0
    magic_resistance_bonus: int = 0
    bonus_melee_damage_bonus: int = 0
    bonus_ranged_damage_bonus: int = 0
    bonus_magic_damage_bonus: int = 0
    bonus_melee_defense_bonus: int = 0
    bonus_ranged_defense_bonus: int = 0
    bonus_magic_defense_bonus: int = 0
    fatigue: int = 0  # Система стомленості
    last_rest_time: Optional[datetime] = None


class Enemy(BaseModel):
    name: str
    stamina: int
    agility: int
    mind: int
    attack: int
    defense: int
    xp_reward: int
    loot: List[str]


class BattleSystem:
    def __init__(self, player: Character, enemy: Enemy):
        self.player = player
        self.enemy = enemy
        self.turn = 1 if player.agility >= enemy.agility else 0
        self.apply_fatigue()

    def apply_fatigue(self):
        if self.player.fatigue >= 5:
            self.player.stamina = int(self.player.stamina * 0.85)
            self.player.energy = int(self.player.energy * 0.85)
            self.player.agility = int(self.player.agility * 0.85)
            self.player.mind = int(self.player.mind * 0.85)

    def attack(self, attacker: Character, defender: Enemy):
        hit_chance = max(10, 75 + attacker.agility - defender.agility)
        if random.randint(1, 100) <= hit_chance:
            critical = random.random() < 0.2  # 20% шанс критичного удару
            damage = max(1, attacker.melee_attack_bonus + attacker.bonus_melee_damage_bonus - defender.defense)
            if critical:
                damage *= 2
                return f"{attacker.name} завдав КРИТИЧНИЙ удар {defender.name} на {damage} урону!"
            defender.stamina -= damage
            return f"{attacker.name} вдарив {defender.name} на {damage} урону!"
        return f"{attacker.name} промахнувся!"

    def magic_attack(self, attacker: Character, defender: Enemy):
        if attacker.energy >= 10:
            attacker.energy -= 10
            damage = max(1, attacker.mind + attacker.bonus_magic_damage_bonus - defender.magic_resistance_bonus)
            defender.stamina -= damage
            return f"{attacker.name} використав магічну атаку на {defender.name}, завдавши {damage} урону!"
        return f"{attacker.name} не має достатньо енергії для магічної атаки!"

    def enemy_attack(self):
        hit_chance = max(10, 75 + self.enemy.agility - self.player.agility)
        if random.randint(1, 100) <= hit_chance:
            damage = max(1, self.enemy.attack - self.player.physical_defense_bonus)
            self.player.stamina -= damage
            return f"{self.enemy.name} атакує {self.player.name} на {damage} урону!"
        return f"{self.enemy.name} промахнувся!"


@app.post("/start_battle/")
def start_battle(player: Character, enemy: Enemy):
    battle = BattleSystem(player, enemy)
    log = []
    while player.stamina > 0 and enemy.stamina > 0:
        if battle.turn == 1:
            action = random.choice(["attack", "magic_attack"]) if player.energy >= 10 else "attack"
            if action == "attack":
                log.append(battle.attack(player, enemy))
            else:
                log.append(battle.magic_attack(player, enemy))
        else:
            log.append(battle.enemy_attack())
        battle.turn = 1 - battle.turn  # Чергування ходів

    winner = player.name if player.stamina > 0 else enemy.name
    log.append(f"Бій завершено! Переможець: {winner}")
    player.fatigue += 1
    return {"log": log}


class RaidBattleSystem:
    def __init__(self, players: List[Character], boss: Enemy):
        self.players = players
        self.boss = boss
        self.turn = 0
        self.apply_fatigue()

    def apply_fatigue(self):
        for player in self.players:
            if player.fatigue >= 5:
                player.stamina = int(player.stamina * 0.85)
                player.energy = int(player.energy * 0.85)
                player.agility = int(player.agility * 0.85)
                player.mind = int(player.mind * 0.85)

    def attack(self, attacker: Character, defender: Enemy):
        hit_chance = max(10, 75 + attacker.agility - defender.agility)
        if random.randint(1, 100) <= hit_chance:
            critical = random.random() < 0.2  # 20% шанс критичного удару
            damage = max(1, attacker.melee_attack_bonus + attacker.bonus_melee_damage_bonus - defender.defense)
            if critical:
                damage *= 2
                return f"{attacker.name} завдав КРИТИЧНИЙ удар {defender.name} на {damage} урону!"
            defender.stamina -= damage
            return f"{attacker.name} вдарив {defender.name} на {damage} урону!"
        return f"{attacker.name} промахнувся!"

    def boss_attack(self):
        target = random.choice(self.players)
        hit_chance = max(10, 75 + self.boss.agility - target.agility)
        if random.randint(1, 100) <= hit_chance:
            damage = max(1, self.boss.attack - target.physical_defense_bonus)
            target.stamina -= damage
            return f"{self.boss.name} атакує {target.name} на {damage} урону!"
        return f"{self.boss.name} промахнувся!"


@app.post("/start_raid/")
def start_raid(players: List[Character], boss: Enemy):
    battle = RaidBattleSystem(players, boss)
    log = []
    while boss.stamina > 0 and any(player.stamina > 0 for player in players):
        if battle.turn < len(players):
            player = players[battle.turn]
            if player.stamina > 0:
                log.append(battle.attack(player, boss))
        else:
            log.append(battle.boss_attack())

        battle.turn = (battle.turn + 1) % (len(players) + 1)  # Чергування ходів

    winner = "Гравці" if boss.stamina <= 0 else "Бос"
    log.append(f"Рейд завершено! Переможець: {winner}")
    for player in players:
        player.fatigue += 1
    return {"log": log}
