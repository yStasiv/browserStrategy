from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from backend.config import ENTERPRISE_SHIFT_DURATION
from backend.models import Enterprise, User
from backend.world_models import PlayerTravel, SectorConnection, WorldSector


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sectors(db):
    return db.scalars(select(WorldSector).order_by(WorldSector.sort_order, WorldSector.key)).all()


def resolve_location(db, player):
    # Serialize arrivals, departures and location-dependent actions even on SQLite.
    db.execute(
        update(User).where(User.id == player.id).values(map_sector=User.map_sector)
        .execution_options(synchronize_session=False)
    )
    db.refresh(player)
    now = utc_now()
    journey = db.get(PlayerTravel, player.id)
    if journey is not None and now >= journey.arrives_at:
        destination = db.get(WorldSector, journey.destination)
        player.map_sector = destination.key
        player.map_x = destination.map_x
        player.map_y = destination.map_y
        db.delete(journey)
        db.flush()
        journey = None
    return journey, now


def is_present(player, journey, sector):
    return journey is None and player.map_sector == sector


def require_presence(db, player, sector):
    journey, _ = resolve_location(db, player)
    if journey is not None:
        db.commit()
        raise HTTPException(409, "Ця дія недоступна під час подорожі.")
    if not is_present(player, journey, sector):
        db.commit()
        raise HTTPException(403, "Для цієї дії потрібно бути у відповідному секторі.")


def working_blocks_travel(db, player, now):
    if not player.workplace or not player.work_start_time:
        return False
    from backend.services.enterprises import active_shift
    shift = active_shift(db, player.id)
    if shift is not None:
        return now < shift.completes_at
    return datetime.now() - player.work_start_time < ENTERPRISE_SHIFT_DURATION


def start_travel(db, player, destination_key):
    journey, now = resolve_location(db, player)
    if journey is not None:
        raise HTTPException(409, "Подорож уже триває.")
    destination = db.get(WorldSector, destination_key)
    if destination is None:
        raise HTTPException(404, "Сектор не знайдено.")
    if not destination.unlocked:
        raise HTTPException(403, "Сектор ще заблокований.")
    route = db.get(SectorConnection, (player.map_sector, destination_key))
    if route is None:
        raise HTTPException(409, "Між цими секторами немає прямого сполучення.")
    if working_blocks_travel(db, player, now):
        raise HTTPException(409, "Під час роботи залишити сектор неможливо.")

    journey = PlayerTravel(
        player_id=player.id, origin=player.map_sector, destination=destination_key,
        started_at=now, arrives_at=now + timedelta(seconds=route.duration_seconds),
    )
    db.add(journey)
    return journey, now


def unlock_sector(db, key):
    sector = db.get(WorldSector, key)
    if sector is None:
        raise HTTPException(404, "Сектор не знайдено.")
    sector.unlocked = True


def set_connection(db, origin, destination, duration_seconds, bidirectional):
    if origin == destination:
        raise HTTPException(422, "Обери різні сектори.")
    if db.get(WorldSector, origin) is None or db.get(WorldSector, destination) is None:
        raise HTTPException(404, "Сектор не знайдено.")
    for source, target in [(origin, destination), (destination, origin)]:
        route = db.get(SectorConnection, (source, target))
        if source == destination and not bidirectional:
            if route is not None:
                db.delete(route)
        elif route is None:
            db.add(SectorConnection(origin=source, destination=target, duration_seconds=duration_seconds))
        else:
            route.duration_seconds = duration_seconds


def utc_timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def map_state(db, player, journey, now):
    from backend.services.enterprises import image_url

    routes = db.scalars(
        select(SectorConnection).where(SectorConnection.origin == player.map_sector)
    ).all()
    durations = {route.destination: route.duration_seconds for route in routes}
    enterprises = [] if journey else db.scalars(
        select(Enterprise).where(Enterprise.sector == player.map_sector).order_by(Enterprise.id)
    ).all()
    return {
        "current_sector": player.map_sector,
        "server_time": utc_timestamp(now),
        "work_blocks_travel": working_blocks_travel(db, player, now),
        "travel": {
            "origin": journey.origin, "destination": journey.destination,
            "started_at": utc_timestamp(journey.started_at), "arrives_at": utc_timestamp(journey.arrives_at),
        } if journey else None,
        "sectors": [
            {
                "key": sector.key, "name": sector.name, "unlocked": sector.unlocked,
                "map_x": sector.map_x, "map_y": sector.map_y,
                "duration_seconds": durations.get(sector.key),
            }
            for sector in sectors(db)
        ],
        "enterprises": [
            {
                "id": entry.id, "name": entry.name, "resource_type": entry.resource_type,
                "production_type": entry.production_type,
                "image_url": image_url(entry),
                "area": entry.area, "salary": entry.salary, "workers_count": entry.workers_count,
                "max_workers": entry.max_workers, "resource_stored": entry.resource_stored,
                "max_storage": entry.max_storage,
            }
            for entry in enterprises
        ],
    }
