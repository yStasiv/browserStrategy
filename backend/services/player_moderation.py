"""Authorization and audit trail for account moderation."""
from datetime import UTC
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from backend.models import PlayerModerationEvent, User
from backend.services.hero_equipment import lock_hero
from backend.services.nicknames import temporary_name
from backend.services.world import utc_now

KYIV = ZoneInfo("Europe/Kyiv")


def can_view_account_status(viewer):
    return bool(viewer and (viewer.is_admin or viewer.is_moderator or viewer.is_system))


def can_moderate(actor, player):
    return bool(actor and (actor.is_admin or actor.is_moderator)
                and actor.id != player.id and not player.is_system
                and (actor.is_admin or not player.is_admin))


def can_assign_moderator(actor, player):
    return bool(actor and actor.is_admin and not player.is_admin and not player.is_system)


def _target(db, player_id):
    player = db.get(User, player_id)
    if player is None or not player.is_active:
        raise HTTPException(404, "Персонажа не знайдено.")
    lock_hero(db, player)
    return player


def set_ban(db, actor, player_id, reason):
    if actor is None or not (actor.is_admin or actor.is_moderator):
        raise HTTPException(403, "Потрібні права адміністратора або модератора.")
    player = _target(db, player_id)
    if not can_moderate(actor, player):
        raise HTTPException(403, "Цього гравця не можна модерувати.")
    if reason is not None:
        reason = reason.strip()
        if not reason or len(reason) > 500:
            raise HTTPException(422, "Вкажи причину блокування до 500 символів.")
    if (player.ban_reason is not None) == (reason is not None):
        raise HTTPException(409, "Статус блокування вже відповідає запиту.")
    player.ban_reason = reason
    if reason is None:
        player.session_id = None
    db.add(PlayerModerationEvent(
        player_id=player.id, actor_id=actor.id, action="block" if reason is not None else "unblock",
        reason=reason, created_at=utc_now(),
    ))


def set_moderator(db, actor, player_id, enabled):
    if actor is None or not actor.is_admin:
        raise HTTPException(403, "Потрібні права адміністратора.")
    player = _target(db, player_id)
    if not can_assign_moderator(actor, player):
        raise HTTPException(403, "Роль цього персонажа не можна змінити.")
    player.is_moderator = enabled


def reset_nickname(db, actor, player_id):
    if actor is None or not (actor.is_admin or actor.is_moderator):
        raise HTTPException(403, "Потрібні права адміністратора або модератора.")
    player = _target(db, player_id)
    if not can_moderate(actor, player):
        raise HTTPException(403, "Цього гравця не можна модерувати.")
    if player.nickname_reset_from is not None:
        raise HTTPException(409, "Гравець уже має тимчасовий нікнейм.")
    player.nickname_reset_from = player.username
    player.username = temporary_name(db, player.id)
    player.session_id = None
    db.add(PlayerModerationEvent(
        player_id=player.id, actor_id=actor.id, action="rename_reset", created_at=utc_now(),
    ))


def history(db, player_id):
    event = PlayerModerationEvent
    return db.query(event).filter(event.player_id == player_id).order_by(
        event.created_at.desc(), event.id.desc(),
    ).all()


def display_entry(event):
    timestamp = event.created_at.replace(tzinfo=UTC).astimezone(KYIV).strftime("%d-%m-%Y %H:%M")
    message = {"block": f"Гравець заблокований: {event.reason}",
               "unblock": "Гравець розблокований", "rename_reset": "Нікнейм гравця скинуто"}[event.action]
    return f"{timestamp} {message}"
