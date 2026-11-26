from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.auth import get_current_user as session_user
from backend.services import guild, world
from backend.database import get_db
from backend.models import User

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    user = await session_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Увійдіть до гри.")
    return user


router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")


class ReplaceQuest(BaseModel):
    confirm_progress_loss: bool = False


@router.get("/guild")
async def guild_page(request: Request, db: Session = Depends(get_db)):
    user = await session_user(request, db)
    if user is None:
        return RedirectResponse(url="/")
    in_castle = guild_present(db, user)
    return templates.TemplateResponse(
        "guild_board.html", {"request": request, "user": user, "in_castle": in_castle}
    )


def guild_present(db, user):
    journey, _ = world.resolve_location(db, user)
    present = world.is_present(user, journey, "Castle")
    db.commit()
    return present


def mutate_board(db, user, operation, *args):
    world.require_presence(db, user, "Castle")
    try:
        operation(db, user.id, *args)
        db.flush()
        result = guild.board(db, user.id)
        db.commit()
    except guild.GuildError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return result


@router.get("/api/guild")
def guild_board(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    world.require_presence(db, user, "Castle")
    result = guild.board(db, user.id)
    db.commit()
    return result


@router.post("/api/guild/initialize")
def initialize_board(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return mutate_board(db, user, guild.initialize)


@router.post("/api/guild/quests/{quest_id}/claim")
def claim_quest(quest_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return mutate_board(db, user, guild.claim, quest_id)


@router.post("/api/guild/quests/{quest_id}/replace")
def replace_quest(
    quest_id: int, body: ReplaceQuest, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return mutate_board(db, user, guild.replace, quest_id, body.confirm_progress_loss)
