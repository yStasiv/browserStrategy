"""Нові ендпоінти бою. Підключення в main.py: app.include_router(battle_api.router)"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, StrictInt
from sqlalchemy.orm import Session

from .. import database
from ..auth import get_current_user
from . import battle_service as svc

router = APIRouter(prefix="/api/battles", tags=["battles"])


class StartPve(BaseModel):
    scenario: str = "training"


class SurrenderIn(BaseModel):
    version: int


class ActionIn(BaseModel):
    version: int   # версія стану, яку бачив клієнт
    action: dict   # {"type": "attack", "target_id": "...", "from_pos": [x, y]} тощо


async def _user(request: Request, db: Session):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _call(fn, *args):
    try:
        return fn(*args)
    except svc.BattleError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@router.post("/pve")
async def start_pve(body: StartPve, request: Request, db: Session = Depends(database.get_db)):
    user = await _user(request, db)
    return _call(svc.start_pve, db, user, body.scenario)


@router.get("/active")
async def active_battle(request: Request, db: Session = Depends(database.get_db)):
    user = await _user(request, db)
    battle_id = svc.get_active_battle_id(db, user.id)
    if battle_id is None:
        raise HTTPException(status_code=404, detail="Немає активного бою")
    return _call(svc.get_battle_view, db, user, battle_id)


@router.get("/history")
async def history(request: Request, db: Session = Depends(database.get_db)):
    return svc.replay_history(db, await _user(request, db))


@router.get("/{battle_id}")
async def get_battle(battle_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = await _user(request, db)
    return _call(svc.get_battle_view, db, user, battle_id)


@router.post("/{battle_id}/actions")
async def post_action(battle_id: int, body: ActionIn, request: Request,
                      db: Session = Depends(database.get_db)):
    user = await _user(request, db)
    return _call(svc.submit_action, db, user, battle_id, body.action, body.version)


@router.post("/{battle_id}/surrender")
async def post_surrender(battle_id: int, body: SurrenderIn, request: Request,
                         db: Session = Depends(database.get_db)):
    user = await _user(request, db)
    return _call(svc.surrender_battle, db, user, battle_id, body.version)


@router.get("/{battle_id}/events")
async def get_events(battle_id: int, request: Request, db: Session = Depends(database.get_db)):
    return _call(svc.battle_events, db, await _user(request, db), battle_id)


@router.get("/{battle_id}/replay")
async def get_replay(battle_id: int, request: Request, db: Session = Depends(database.get_db)):
    try:
        return svc.battle_events(db, await _user(request, db), battle_id, finished_only=True)
    except svc.BattleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/{battle_id}/auto")
async def auto_action(battle_id: int, body: SurrenderIn, request: Request, db: Session = Depends(database.get_db)):
    return _call(svc.submit_auto_action, db, await _user(request, db), battle_id, body.version)


class PlacementIn(BaseModel):
    version: int
    stack_id: str
    x: StrictInt
    y: StrictInt
    split_count: StrictInt | None = None


@router.post("/{battle_id}/deployment")
async def deploy(battle_id: int, body: PlacementIn, request: Request, db: Session = Depends(database.get_db)):
    return _call(svc.update_deployment, db, await _user(request, db), battle_id, body.version,
                 (body.stack_id, body.x, body.y, body.split_count))


@router.post("/{battle_id}/begin")
async def begin(battle_id: int, body: SurrenderIn, request: Request, db: Session = Depends(database.get_db)):
    return _call(svc.update_deployment, db, await _user(request, db), battle_id, body.version)
