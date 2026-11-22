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
from collections import deque
from typing import Dict, List, Optional, Tuple

from .actions import Attack, Defend, Move, Skip, Summon, Wait
from .data import UNITS
from .state import ATB_SCALE, MAX_ACTIONS, BattleState, Stack
from .summoning import spawn_position, squad_health

Cell = Tuple[int, int]

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

def _bfs(state: BattleState, stack: Stack):
    speed = UNITS[stack.unit].speed
    blocked = {c for s in state.stacks.values() if s.id != stack.id for c in s.cells()}
    w, h = stack.w, stack.h

    def fits(x: int, y: int) -> bool:
        if x < 0 or y < 0 or x + w > state.width or y + h > state.height:
            return False
        return all((x + i, y + j) not in blocked for i in range(w) for j in range(h))

    start = (stack.x, stack.y)
    dist: Dict[Cell, int] = {start: 0}
    parent: Dict[Cell, Cell] = {}
    q = deque([start])
    while q:
        cur = q.popleft()
        d = dist[cur]
        if d == speed:
            continue
        for dx, dy in DIRS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in dist or not fits(*nxt):
                continue
            dist[nxt] = d + 1
            parent[nxt] = cur
            q.append(nxt)
    return dist, parent


def reachable(state: BattleState, stack: Stack) -> Dict[Cell, int]:
    """Позиції (лівий верхній кут), куди може стати загін, з відстанню в кроках (включно з поточною)."""
    return _bfs(state, stack)[0]


def _path(state: BattleState, stack: Stack, dest: Cell) -> List[List[int]]:
    _, parent = _bfs(state, stack)
    path = [dest]
    while path[-1] in parent:
        path.append(parent[path[-1]])
    return [list(c) for c in reversed(path)]


# ---------- стрільба ----------

def has_adjacent_enemy(state: BattleState, stack: Stack) -> bool:
    return any(e.owner != stack.owner and dist_stacks(stack, e) == 1 for e in state.stacks.values())


def is_ranged(state: BattleState, stack: Stack) -> bool:
    """Стрілець стріляє лише якщо поруч (у сусідній клітинці) немає ворога.
    Інакше він б'ється врукопашну: може йти й атакувати, отримує контратаку, постріли не витрачає."""
    return stack.shots_left > 0 and not has_adjacent_enemy(state, stack)


# ---------- шкода ----------

def _multiplier(att_stack: Stack, def_stack: Stack) -> float:
    a = UNITS[att_stack.unit].attack
    d = UNITS[def_stack.unit].defense
    if def_stack.defending:
        d *= 1.3
    diff = a - d
    if diff > 0:
        return 1 + min(0.05 * diff, 3.0)
    return 1 - min(0.025 * -diff, 0.7)


def shot_multiplier(att: Stack, target: Stack) -> int:
    return 2 if dist_stacks(att, target) <= UNITS[att.unit].shooting_range else 1


def expected_damage(att: Stack, target: Stack, *, ranged=False) -> float:
    u = UNITS[att.unit]
    damage = (u.dmg_min + u.dmg_max) / 2 * att.count * _multiplier(att, target)
    return damage * shot_multiplier(att, target) if ranged else damage


def _roll_damage(att: Stack, target: Stack, rng: random.Random) -> int:
    u = UNITS[att.unit]
    n = min(att.count, 10)  # для великих загонів кидаємо до 10 кубиків і масштабуємо
    total = sum(rng.randint(u.dmg_min, u.dmg_max) for _ in range(n))
    base = total * att.count / n
    return max(1, int(base * _multiplier(att, target)))


def total_hp(stack: Stack) -> int:
    return (stack.count - 1) * UNITS[stack.unit].hp + stack.top_hp if stack.count > 0 else 0


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

def period(stack: Stack) -> int:
    return ATB_SCALE // UNITS[stack.unit].initiative


def _tiebreak(stack: Stack, seq: int) -> int:
    return (stack.owner + seq) % 2  # при рівному ready сторони чергуються


def _pick_active(state: BattleState) -> str:
    return min(state.stacks.values(), key=lambda s: (s.ready, _tiebreak(s, state.seq), s.id)).id


def init_timeline(state: BattleState) -> None:
    for s in state.stacks.values():
        s.ready = period(s)
    state.active_id = _pick_active(state)


def _finish(state: BattleState, events: list, winner: Optional[int], reason: Optional[str] = None) -> None:
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
    a = state.stacks[state.active_id]
    a.defending = False      # захист діє до власного наступного ходу
    a.retaliated = False     # контратака відновлюється на початку власного ходу


def _end_turn(state: BattleState, actor: Stack, events: list) -> None:
    if actor.id in state.stacks:  # загін міг загинути від контратаки
        actor.ready += period(actor)
    _advance(state, events)


# ---------- дії ----------

def _do_move(st: BattleState, actor: Stack, a: Move, events: list) -> None:
    dest = (a.x, a.y)
    if dest == (actor.x, actor.y) or dest not in reachable(st, actor):
        raise IllegalAction("клітинка недосяжна")
    events.append({"type": "move", "stack": actor.id, "path": _path(st, actor, dest)})
    actor.x, actor.y = dest
    _end_turn(st, actor, events)


def _do_attack(st: BattleState, actor: Stack, a: Attack, rng: random.Random, events: list) -> None:
    target = st.stacks.get(a.target_id)
    if target is None or target.owner == actor.owner:
        raise IllegalAction("некоректна ціль")

    ranged = is_ranged(st, actor)
    if ranged:
        if a.from_pos and tuple(a.from_pos) != (actor.x, actor.y):
            raise IllegalAction("стрілець не може рухатись і стріляти в один хід")
    else:
        pos = tuple(a.from_pos) if a.from_pos else (actor.x, actor.y)
        if pos not in reachable(st, actor):
            raise IllegalAction("клітинка недосяжна")
        if rect_dist(pos[0], pos[1], actor.w, actor.h, target.x, target.y, target.w, target.h) != 1:
            raise IllegalAction("ціль не поруч")
        if pos != (actor.x, actor.y):
            events.append({"type": "move", "stack": actor.id, "path": _path(st, actor, pos)})
            actor.x, actor.y = pos

    hp_before = total_hp(target)
    dmg = _roll_damage(actor, target, rng)
    if ranged:
        dmg *= shot_multiplier(actor, target)
    killed = _hurt(target, dmg)
    if ranged:
        actor.shots_left -= 1
    events.append({"type": "attack", "attacker": actor.id, "target": target.id,
                   "damage": dmg, "killed": killed, "ranged": ranged,
                   "target_left": target.count, "top_hp": target.top_hp,
                   "hp_before": hp_before, "hp_after": total_hp(target)})

    if target.count <= 0:
        del st.stacks[target.id]
    elif not ranged and not target.retaliated:
        target.retaliated = True
        hp_before = total_hp(actor)
        rdmg = _roll_damage(target, actor, rng)
        rkilled = _hurt(actor, rdmg)
        events.append({"type": "retaliation", "attacker": target.id, "target": actor.id,
                       "damage": rdmg, "killed": rkilled, "target_left": actor.count, "top_hp": actor.top_hp,
                       "hp_before": hp_before, "hp_after": total_hp(actor)})
        if actor.count <= 0:
            del st.stacks[actor.id]
    _end_turn(st, actor, events)


def _do_summon(state, actor, action, events):
    magic = state.summoning.get(str(actor.owner))
    if not magic or action.element not in magic["elements"]:
        raise IllegalAction("Цей виклик недоступний.")
    if magic["energy"] < magic["cost"]:
        raise IllegalAction("Недостатньо енергії для виклику.")
    previous = next((s for s in state.stacks.values() if s.owner == actor.owner and s.summoned), None)
    unit = UNITS[f"elemental_{action.element}"]
    position = spawn_position(state, unit, previous)
    if position is None:
        raise IllegalAction("На полі немає місця для елементаля.")
    count, top_hp = squad_health(magic["hp_pool"], unit.hp)
    if not count:
        raise IllegalAction("Недостатньо сили магії для виклику.")

    if previous:
        del state.stacks[previous.id]
    stack = Stack(
        id=f"summon_{actor.owner}_{state.seq}", unit=unit.key, owner=actor.owner,
        count=count, top_hp=top_hp, x=position[0], y=position[1],
        w=unit.size[0], h=unit.size[1], shots_left=unit.shots, summoned=True,
    )
    stack.ready = actor.ready + period(stack)
    state.stacks[stack.id] = stack
    magic["energy"] -= magic["cost"]
    events.append({
        "type": "summon", "stack": actor.id, "target": stack.id, "unit": unit.key,
        "count": count, "top_hp": top_hp, "unit_hp": unit.hp,
        "replaced": previous.id if previous else None, "energy": magic["energy"],
    })
    _end_turn(state, actor, events)


def apply(state: BattleState, action) -> Tuple[BattleState, List[dict]]:
    if state.status != "active" or state.active_id is None:
        raise IllegalAction("бій завершено")
    st = copy.deepcopy(state)
    rng = random.Random(f"{st.seed}:{st.seq}")
    st.seq += 1
    actor = st.stacks[st.active_id]
    events: List[dict] = []

    if isinstance(action, Move):
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
        if actor.waited:
            raise IllegalAction("чекати можна лише один раз за бій")
        actor.waited = True
        actor.ready += period(actor) // 2   # діятиме пізніше, але раніше за повний період
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
    """Що може зробити активний загін: позиції руху та цілі з позиціями для удару."""
    actor = state.active()
    if actor is None:
        return None
    dist = reachable(state, actor)
    ranged = is_ranged(state, actor)
    targets = []
    for e in state.stacks.values():
        if e.owner == actor.owner:
            continue
        if ranged:
            targets.append({"id": e.id, "from": [[actor.x, actor.y]]})
        else:
            cells = [list(p) for p in dist
                     if rect_dist(p[0], p[1], actor.w, actor.h, e.x, e.y, e.w, e.h) == 1]
            if cells:
                targets.append({"id": e.id, "from": cells})
    return {
        "active": actor.id,
        "owner": actor.owner,
        "move": [list(c) for c in dist if c != (actor.x, actor.y)],
        "targets": targets,
        "can_wait": not actor.waited,
        "ranged": ranged,   # False у стрільця з ворогом поруч — він б'ється врукопашну
    }


def forecast(state: BattleState, n: int = 50) -> List[dict]:
    """Прогноз черги на n наступних ходів: [{"id": ...}].
    Припускає, що кожен загін просто робить звичайну дію (без втрат і «чекати»), тож це орієнтир."""
    if state.status != "active" or state.active_id is None:
        return []
    ready = {s.id: s.ready for s in state.stacks.values()}
    periods = {s.id: period(s) for s in state.stacks.values()}
    owner = {s.id: s.owner for s in state.stacks.values()}
    out: List[dict] = []
    cur = state.active_id
    seq = state.seq
    for _ in range(n):
        out.append({"id": cur})
        ready[cur] += periods[cur]
        seq += 1
        cur = min(ready, key=lambda i: (ready[i], (owner[i] + seq) % 2, i))
    return out
