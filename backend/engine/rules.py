"""Правила бою. Чисті функції: без БД, без HTTP, без print.

apply(state, action) -> (новий_стан, події). Вхідний стан не змінюється.
Випадковість детермінована: Random(f"{seed}:{seq}") — той самий стан + дія дають той самий результат.

Загін займає прямокутник w x h клітинок; (x, y) — його лівий верхній кут.
Раундів немає: діє загін із найменшим `ready`, після дії `ready` росте на період (ATB_SCALE // ініціатива).
"""
from __future__ import annotations

import copy
import math
import random
from heapq import heappop, heappush
from typing import Dict, List, Optional, Tuple

from .actions import Attack, Defend, Move, Skip, Summon, Wait
from .data import DEFAULT_SHOOTING_RANGE, UNITS
from .state import ATB_SCALE, MAX_ACTIONS, BattleState, HeroTurn, Stack
from .squad_effects import roll_squad_stat, squad_stat, total_hp
from .summoning import spell_options, summon_plan

Cell = Tuple[int, int]
ORTHOGONAL_COST = 10
DIAGONAL_COST = 15

# Рух і суміжність у 8 напрямках (з діагоналями). Для 4 напрямків залиште лише осі.
DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]


class IllegalAction(ValueError):
    pass


# ---------- геометрія ----------

def cheb(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(ax - bx), abs(ay - by))


def rect_dist(ax: int, ay: int, aw: int, ah: int, bx: int, by: int, bw: int, bh: int) -> int:
    """Відстань між прямокутниками в «ходах короля». 1 = стикаються (в т.ч. по діагоналі)."""
    dx = max(bx - (ax + aw - 1), ax - (bx + bw - 1))
    dy = max(by - (ay + ah - 1), ay - (by + bh - 1))
    return max(dx, dy)


def dist_stacks(a: Stack, b: Stack) -> int:
    return rect_dist(a.x, a.y, a.w, a.h, b.x, b.y, b.w, b.h)


# ---------- пересування ----------

def _movement(state: BattleState, stack: Stack):
    unit = UNITS[stack.unit]
    budget = unit.speed * ORTHOGONAL_COST
    blocked = state.blocked_cells(excluding=stack.id)
    w, h = stack.w, stack.h

    def fits(x: int, y: int) -> bool:
        return (0 <= x <= state.width - w and 0 <= y <= state.height - h
                and all((x + i, y + j) not in blocked for i in range(w) for j in range(h)))

    start = (stack.x, stack.y)
    costs: Dict[Cell, int] = {start: 0}
    parents: Dict[Cell, Cell] = {}
    if "flying" in unit.abilities:
        for y in range(state.height - h + 1):
            for x in range(state.width - w + 1):
                dx, dy = abs(x - start[0]), abs(y - start[1])
                cost = DIAGONAL_COST * min(dx, dy) + ORTHOGONAL_COST * abs(dx - dy)
                if 0 < cost <= budget and fits(x, y):
                    costs[x, y] = cost
                    parents[x, y] = start
        return costs, parents

    queue = [(0, start)]
    while queue:
        cost, current = heappop(queue)
        if cost != costs[current]:
            continue
        x, y = current
        for dx, dy in DIRS:
            diagonal = dx != 0 and dy != 0
            next_cost = cost + (DIAGONAL_COST if diagonal else ORTHOGONAL_COST)
            destination = (x + dx, y + dy)
            if next_cost > budget or next_cost >= costs.get(destination, budget + 1) or not fits(*destination):
                continue
            if diagonal and not (fits(x + dx, y) or fits(x, y + dy)):
                continue
            costs[destination] = next_cost
            parents[destination] = current
            heappush(queue, (next_cost, destination))
    return costs, parents


def reachable(state: BattleState, stack: Stack) -> Dict[Cell, int]:
    """Доступні позиції лівого верхнього кута загону та їхня найменша вартість руху."""
    return _movement(state, stack)[0]


def _path(parents: Dict[Cell, Cell], destination: Cell) -> List[List[int]]:
    path = [destination]
    while path[-1] in parents:
        path.append(parents[path[-1]])
    return [list(cell) for cell in reversed(path)]


def _move_stack(stack, destination, path, cost, events):
    events.append({
        "type": "move", "stack": stack.id, "path": path,
        "move_points": cost, "flying": "flying" in UNITS[stack.unit].abilities,
    })
    stack.x, stack.y = destination


# ---------- стрільба ----------

def has_adjacent_enemy(state: BattleState, stack: Stack) -> bool:
    return any(e.owner != stack.owner and dist_stacks(stack, e) == 1 for e in state.stacks.values())


def is_ranged(state: BattleState, stack: Stack) -> bool:
    """Стрілець стріляє лише якщо поруч (у сусідній клітинці) немає ворога.
    Інакше він б'ється врукопашну: може йти й атакувати, отримує контратаку, постріли не витрачає."""
    return ("ranged_attack" in UNITS[stack.unit].abilities
            and stack.shots_left > 0 and not has_adjacent_enemy(state, stack))


# ---------- шкода ----------

def _multiplier(att_stack: Stack, def_stack: Stack) -> float:
    diff = UNITS[att_stack.unit].attack - effective_defense(def_stack)
    return min(4.0, 1.0 + 0.05 * diff) if diff >= 0 else max(0.3, 1.0 + 0.025 * diff)


def effective_defense(target: Stack) -> float:
    defense = UNITS[target.unit].defense
    return defense * 1.3 if target.defending else defense


def scaled_damage(base, multiplier):
    return max(1, math.floor(base * multiplier))


def attack_preview(att: Stack, target: Stack, *, ranged: bool) -> dict:
    unit = UNITS[att.unit]
    mult = _multiplier(att, target)
    shot = shot_multiplier(att, target) if ranged else 1
    base_min, base_max = att.count * unit.dmg_min, att.count * unit.dmg_max
    final_min = scaled_damage(base_min, mult) * shot
    final_max = scaled_damage(base_max, mult) * shot
    return {
        "base_dmg_min": base_min, "base_dmg_max": base_max,
        "roll_count": min(att.count, 10), "roll_scale": att.count / min(att.count, 10),
        "eff_def": effective_defense(target), "mult": mult,
        "can_shoot": ranged, "is_double_shot": shot == 2,
        "final_dmg_min": final_min, "final_dmg_max": final_max,
        "average_damage": scaled_damage((base_min + base_max) / 2, mult) * shot,
        "unit_dmg_min": scaled_damage(unit.dmg_min, mult * shot),
        "unit_dmg_max": scaled_damage(unit.dmg_max, mult * shot),
        "estimated_kills": min(target.count, final_max // UNITS[target.unit].hp),
        "will_counterattack": not ranged and not target.retaliated and final_min < total_hp(target),
    }


def shot_multiplier(att: Stack, target: Stack) -> int:
    return 2 if dist_stacks(att, target) <= DEFAULT_SHOOTING_RANGE else 1


def expected_damage(att: Stack, target: Stack, *, ranged=False) -> float:
    u = UNITS[att.unit]
    damage = (u.dmg_min + u.dmg_max) / 2 * att.count * _multiplier(att, target)
    return damage * shot_multiplier(att, target) if ranged else damage


def _roll_damage(att: Stack, target: Stack, rng: random.Random) -> int:
    u = UNITS[att.unit]
    n = min(att.count, 10)  # для великих загонів кидаємо до 10 кубиків і масштабуємо
    total = sum(rng.randint(u.dmg_min, u.dmg_max) for _ in range(n))
    base = total * att.count / n
    return scaled_damage(base, _multiplier(att, target))


def _hurt(stack: Stack, dmg: int) -> int:
    """Завдає шкоду загону. Повертає, скільки істот загинуло."""
    hp = UNITS[stack.unit].hp
    pool = total_hp(stack) - dmg
    old = stack.count
    if pool <= 0:
        stack.count = 0
        stack.top_hp = 0
    else:
        stack.count = math.ceil(pool / hp)
        stack.top_hp = pool - (stack.count - 1) * hp
    return old - stack.count


# ---------- черга ходів (шкала готовності) ----------

def period(actor: Stack | HeroTurn) -> int:
    initiative = actor.initiative if isinstance(actor, HeroTurn) else UNITS[actor.unit].initiative
    return ATB_SCALE // initiative


def wait_delay(actor: Stack) -> int:
    return max(1, period(actor) // 2)


def _tiebreak(stack: Stack | HeroTurn, seq: int) -> int:
    return (stack.owner + seq) % 2  # при рівному ready сторони чергуються


def _pick_active(state: BattleState) -> str:
    return min(state.actors(), key=lambda s: (s.ready, _tiebreak(s, state.seq), s.id)).id


def init_timeline(state: BattleState) -> None:
    state.initial_ready_at = {}
    if state.heroes:
        for stack in state.stacks.values():
            stack.luck = squad_stat(state, stack, "luck")
            stack.morale = squad_stat(state, stack, "morale")
    for s in state.actors():
        interval = period(s)
        rng = random.Random(f"{state.seed}:initiative:{s.id}")
        variance = interval // 10
        s.ready = interval + rng.randint(-variance, variance)
        state.initial_ready_at[s.id] = s.ready
    state.active_id = _pick_active(state)


def _finish(state: BattleState, events: list, winner: Optional[int], reason: Optional[str] = None) -> None:
    state.stacks = {key: stack for key, stack in state.stacks.items() if not stack.summoned}
    state.status = "finished"
    state.winner = winner
    state.active_id = None
    ev = {"type": "battle_end", "winner": winner}
    if reason:
        ev["reason"] = reason
    events.append(ev)


def _advance(state: BattleState, events: list) -> None:
    """Перевіряє кінець бою й обирає наступний загін."""
    alive = {s.owner for s in state.stacks.values()}
    if len(alive) < 2:
        _finish(state, events, next(iter(alive)) if alive else None)
        return
    if state.seq >= MAX_ACTIONS:
        _finish(state, events, None, "max_actions")
        return
    state.active_id = _pick_active(state)
    a = state.stacks.get(state.active_id)
    if a is not None:
        a.defending = False      # захист діє до власного наступного ходу
        a.retaliated = False     # контратака відновлюється на початку власного ходу


def _end_turn(state: BattleState, actor: Stack | HeroTurn, events: list) -> None:
    if actor.id in state.stacks or actor.id in state.heroes:  # загін міг загинути від контратаки
        interval = period(actor)
        before = actor.ready
        morale = roll_squad_stat(state, actor, "morale", events) if isinstance(actor, Stack) else 0
        actor.ready += max(1, interval // 2) if morale > 0 else interval + (interval // 2 if morale < 0 else 0)
        if events and events[-1]["type"] == "morale":
            events[-1].update(ready_before=before, normal_ready_at=before + interval, next_ready_at=actor.ready)
    _advance(state, events)


# ---------- дії ----------

def _do_move(st: BattleState, actor: Stack, a: Move, events: list) -> None:
    dest = (a.x, a.y)
    costs, parents = _movement(st, actor)
    if dest == (actor.x, actor.y) or dest not in costs:
        raise IllegalAction("клітинка недосяжна")
    _move_stack(actor, dest, _path(parents, dest), costs[dest], events)
    _end_turn(st, actor, events)


def _apply_luck(state, stack, damage, events):
    luck = roll_squad_stat(state, stack, "luck", events)
    adjusted = damage * 2 if luck > 0 else max(1, damage // 2) if luck < 0 else damage
    if events and events[-1]["type"] == "luck":
        events[-1].update(damage_before=damage, damage_after=adjusted)
    return adjusted


def _do_attack(st: BattleState, actor: Stack, a: Attack, rng: random.Random, events: list) -> None:
    target = st.stacks.get(a.target_id)
    if target is None or target.owner == actor.owner:
        raise IllegalAction("некоректна ціль")

    ranged = is_ranged(st, actor) and not a.force_melee
    if ranged:
        if a.from_pos and tuple(a.from_pos) != (actor.x, actor.y):
            raise IllegalAction("стрілець не може рухатись і стріляти в один хід")
    else:
        pos = tuple(a.from_pos) if a.from_pos else (actor.x, actor.y)
        costs, parents = _movement(st, actor)
        if pos not in costs:
            raise IllegalAction("клітинка недосяжна")
        if rect_dist(pos[0], pos[1], actor.w, actor.h, target.x, target.y, target.w, target.h) != 1:
            raise IllegalAction("ціль не поруч")
        if pos != (actor.x, actor.y):
            _move_stack(actor, pos, _path(parents, pos), costs[pos], events)

    hp_before = total_hp(target)
    dmg = _roll_damage(actor, target, rng)
    shot = shot_multiplier(actor, target) if ranged else 1
    dmg = _apply_luck(st, actor, dmg * shot, events)
    killed = _hurt(target, dmg)
    if ranged:
        actor.shots_left -= 1
    events.append({"type": "attack", "attacker": actor.id, "target": target.id,
                   "damage": dmg, "killed": killed, "ranged": ranged,
                   "distance": dist_stacks(actor, target), "double_damage": shot == 2,
                   "target_left": target.count, "top_hp": target.top_hp,
                   "hp_before": hp_before, "hp_after": total_hp(target)})

    if target.count <= 0:
        del st.stacks[target.id]
    elif not ranged and not target.retaliated:
        target.retaliated = True
        hp_before = total_hp(actor)
        rdmg = _apply_luck(st, target, _roll_damage(target, actor, rng), events)
        rkilled = _hurt(actor, rdmg)
        events.append({"type": "retaliation", "attacker": target.id, "target": actor.id,
                       "damage": rdmg, "killed": rkilled, "target_left": actor.count,
                       "distance": 1, "double_damage": False, "top_hp": actor.top_hp,
                       "hp_before": hp_before, "hp_after": total_hp(actor)})
        if actor.count <= 0:
            del st.stacks[actor.id]
    _end_turn(st, actor, events)


def _do_summon(state, actor, action, events):
    if state.heroes and not isinstance(actor, HeroTurn):
        raise IllegalAction("Викликати елементаля можна лише під час ходу героя.")
    try:
        previous, unit, position, count, top_hp = summon_plan(state, actor.owner, action.element)
    except ValueError as exc:
        raise IllegalAction(str(exc)) from exc
    magic = state.summoning[str(actor.owner)]

    if previous:
        del state.stacks[previous.id]
    stack = Stack(
        id=f"summon_{actor.owner}_{state.seq}", unit=unit.key, owner=actor.owner,
        count=count, top_hp=top_hp, x=position[0], y=position[1],
        w=unit.size[0], h=unit.size[1], shots_left=unit.shots, summoned=True, initial_count=count,
    )
    stack.luck = squad_stat(state, stack, "luck")
    stack.morale = squad_stat(state, stack, "morale")
    stack.ready = actor.ready + period(stack)
    state.stacks[stack.id] = stack
    magic["energy"] -= magic["cost"]
    events.append({
        "type": "summon", "stack": actor.id, "target": stack.id, "unit": unit.key,
        "count": count, "top_hp": top_hp, "unit_hp": unit.hp,
        "replaced": previous.id if previous else None, "energy": magic["energy"],
        "position": position, "spell": action.element, "summon_id": stack.id,
        "spawn_pos": position, "summon_ready_at": stack.ready,
    })
    _end_turn(state, actor, events)


def _hero_action(state, hero, action, rng, events):
    if isinstance(action, Summon):
        _do_summon(state, hero, action, events)
        return
    if isinstance(action, Attack):
        target = state.stacks.get(action.target_id)
        if target is None or target.owner == hero.owner or action.from_pos is not None or action.force_melee:
            raise IllegalAction("Некоректна ціль героя.")
        hp_before = total_hp(target)
        damage = rng.randint(hero.damage_min, hero.damage_max)
        killed = _hurt(target, damage)
        events.append({
            "type": "hero_attack", "attacker": hero.id, "target": target.id,
            "damage": damage, "killed": killed, "ranged": True,
            "target_left": target.count, "top_hp": target.top_hp,
            "hp_before": hp_before, "hp_after": total_hp(target),
        })
        if not target.count:
            del state.stacks[target.id]
    elif isinstance(action, Skip):
        events.append({"type": "skip", "stack": hero.id})
    else:
        raise IllegalAction("Герой може атакувати або застосувати закляття.")
    _end_turn(state, hero, events)


def apply(state: BattleState, action) -> Tuple[BattleState, List[dict]]:
    if state.status != "active" or state.active_id is None:
        raise IllegalAction("бій завершено")
    st = copy.deepcopy(state)
    rng = random.Random(f"{st.seed}:{st.seq}")
    st.seq += 1
    actor = st.active()
    events: List[dict] = []

    if isinstance(actor, HeroTurn):
        _hero_action(st, actor, action, rng, events)
    elif isinstance(action, Move):
        _do_move(st, actor, action, events)
    elif isinstance(action, Attack):
        _do_attack(st, actor, action, rng, events)
    elif isinstance(action, Summon):
        _do_summon(st, actor, action, events)
    elif isinstance(action, Defend):
        actor.defending = True
        events.append({"type": "defend", "stack": actor.id})
        _end_turn(st, actor, events)
    elif isinstance(action, Wait):
        actor.ready += wait_delay(actor)
        events.append({"type": "wait", "stack": actor.id})
        _advance(st, events)
    elif isinstance(action, Skip):          # у UI немає; лишається для автоходу при таймауті
        events.append({"type": "skip", "stack": actor.id})
        _end_turn(st, actor, events)
    else:
        raise IllegalAction("невідома дія")
    return st, events


def surrender(state: BattleState, side: int) -> Tuple[BattleState, List[dict]]:
    """Здатися можна в будь-який момент, не лише у свій хід."""
    if state.status != "active":
        raise IllegalAction("бій завершено")
    if side not in (0, 1):
        raise IllegalAction("невідома сторона")
    st = copy.deepcopy(state)
    st.seq += 1
    st.surrendered = side
    events: List[dict] = [{"type": "surrender", "side": side}]
    _finish(st, events, 1 - side, "surrender")
    return st, events


# ---------- підказки для інтерфейсу ----------

def turn_info(state: BattleState) -> Optional[dict]:
    """Що може зробити активний учасник бою."""
    actor = state.active()
    if actor is None:
        return None
    if isinstance(actor, HeroTurn):
        return {
            "active": actor.id, "owner": actor.owner, "hero": True, "move": [],
            "targets": [{"id": stack.id, "from": []} for stack in state.stacks.values() if stack.owner != actor.owner],
            "can_wait": False, "ranged": True,
            "spells": spell_options(state, actor.owner),
        }
    dist, parents = _movement(state, actor)
    ranged = is_ranged(state, actor)
    targets = []
    for e in state.stacks.values():
        if e.owner == actor.owner:
            continue
        cells = [list(p) for p in dist
                 if rect_dist(p[0], p[1], actor.w, actor.h, e.x, e.y, e.w, e.h) == 1]
        if ranged or cells:
            targets.append({
                "id": e.id, "from": [[actor.x, actor.y]] if ranged else cells,
                "melee_from": cells,
                "preview": attack_preview(actor, e, ranged=ranged),
                "melee_preview": attack_preview(actor, e, ranged=False) if ranged and cells else None,
            })
    return {
        "active": actor.id,
        "owner": actor.owner,
        "move": [list(cell) for cell in parents],
        "move_points": UNITS[actor.unit].speed * ORTHOGONAL_COST,
        "flying": "flying" in UNITS[actor.unit].abilities,
        "move_paths": {f"{x},{y}": {"cost": dist[x, y], "path": _path(parents, (x, y))}
                       for x, y in parents},
        "targets": targets,
        "can_wait": True,
        "can_shoot": ranged,
        "shooting_blocked": "ranged_attack" in UNITS[actor.unit].abilities and actor.shots_left > 0 and not ranged,
        "ranged": ranged,   # False у стрільця з ворогом поруч — він б'ється врукопашну
        **({"spells": spell_options(state, actor.owner)} if not state.heroes and state.summoning else {}),
    }


def forecast(state: BattleState, n: int = 50, *, after_wait: bool = False) -> List[dict]:
    """Прогноз черги на n наступних ходів: [{"id": ...}].
    Припускає, що кожен загін просто робить звичайну дію (без втрат і «чекати»), тож це орієнтир."""
    if state.status != "active" or state.active_id is None:
        return []
    actors = list(state.actors())
    ready = {s.id: s.ready for s in actors}
    periods = {s.id: period(s) for s in actors}
    owner = {s.id: s.owner for s in actors}
    out: List[dict] = []
    cur = state.active_id
    seq = state.seq
    if after_wait:
        actor = state.stacks.get(cur)
        if actor is None or seq + 1 >= MAX_ACTIONS:
            return []
        ready[cur] += wait_delay(actor)
        seq += 1
        cur = min(ready, key=lambda i: (ready[i], (owner[i] + seq) % 2, i))
    for _ in range(n):
        out.append({"id": cur})
        ready[cur] += periods[cur]
        seq += 1
        cur = min(ready, key=lambda i: (ready[i], (owner[i] + seq) % 2, i))
    return out
