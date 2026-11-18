"""Дії гравця. Дія завжди стосується активного загону (queue[0])."""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Move:
    x: int
    y: int


@dataclass(frozen=True)
class Attack:
    target_id: str
    # Ближній бій: клітинка, з якої б'ємо (загін спершу йде туди). None = б'ємо з місця.
    from_pos: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class Wait:
    pass


@dataclass(frozen=True)
class Defend:
    pass


@dataclass(frozen=True)
class Skip:
    pass


Action = (Move, Attack, Wait, Defend, Skip)


def action_from_dict(d: dict):
    """Для API: {"type": "attack", "target_id": "...", "from_pos": [x, y]}"""
    t = d.get("type")
    if t == "move":
        return Move(int(d["x"]), int(d["y"]))
    if t == "attack":
        fp = d.get("from_pos")
        return Attack(str(d["target_id"]), tuple(fp) if fp else None)
    if t == "wait":
        return Wait()
    if t == "defend":
        return Defend()
    if t == "skip":
        return Skip()
    raise ValueError(f"unknown action type: {t!r}")


def action_to_dict(a) -> dict:
    """Для логу дій у БД; зворотна до action_from_dict."""
    if isinstance(a, Move):
        return {"type": "move", "x": a.x, "y": a.y}
    if isinstance(a, Attack):
        return {"type": "attack", "target_id": a.target_id,
                "from_pos": list(a.from_pos) if a.from_pos else None}
    for cls, name in ((Wait, "wait"), (Defend, "defend"), (Skip, "skip")):
        if isinstance(a, cls):
            return {"type": name}
    raise ValueError(f"unknown action: {a!r}")
