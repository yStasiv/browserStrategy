from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update

from backend.config import ENTERPRISE_SHIFT_DURATION
from backend.models import Enterprise, User
from backend.services import map_config
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
        player.map_x, player.map_y = map_config.marker_position(destination.key) or (destination.map_x, destination.map_y)
        db.delete(journey)
        db.flush()
        journey = None
    return journey, now


def is_present(player, journey, sector):
    return journey is None and player.map_sector == sector


def location_available(db, key, feature=None):
    sector = db.get(WorldSector, key)
    return bool(sector and sector.unlocked and (feature is None or map_config.supports(key, feature)))


def require_presence(db, player, sector, feature=None):
    journey, _ = resolve_location(db, player)
    if journey is not None:
        db.commit()
        raise HTTPException(409, "Ця дія недоступна під час подорожі.")
    if not is_present(player, journey, sector) or not location_available(db, sector, feature):
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


def routes_from(db, key):
    durations = dict(map_config.routes_from(key))
    legacy = db.execute(select(SectorConnection.destination, SectorConnection.duration_seconds).where(
        SectorConnection.origin == key, SectorConnection.managed_by_config.is_(False),
    ))
    configured = map_config.by_key()
    durations.update((destination, seconds) for destination, seconds in legacy
                     if key not in configured or destination not in configured or destination in durations)
    return durations


def start_travel(db, player, destination_key):
    lock_world(db)
    journey, now = resolve_location(db, player)
    if journey is not None:
        raise HTTPException(409, "Подорож уже триває.")
    destination = db.get(WorldSector, destination_key)
    if destination is None:
        raise HTTPException(404, "Сектор не знайдено.")
    if not destination.unlocked or not location_available(db, player.map_sector):
        raise HTTPException(403, "Сектор ще заблокований.")
    duration = routes_from(db, player.map_sector).get(destination_key)
    if duration is None:
        raise HTTPException(409, "Між цими секторами немає прямого сполучення.")
    if working_blocks_travel(db, player, now):
        raise HTTPException(409, "Під час роботи залишити сектор неможливо.")

    journey = PlayerTravel(
        player_id=player.id, origin=player.map_sector, destination=destination_key,
        started_at=now, arrives_at=now + timedelta(seconds=duration),
    )
    db.add(journey)
    return journey, now


def unlock_sector(db, key, actor_id=None):
    return unlock_location(db, actor_id, key=key)


def lock_world(db):
    capital = next(row for row in map_config.by_key().values() if row["unlocked_by_default"])
    db.execute(update(WorldSector).where(WorldSector.key == capital["key"])
               .values(sort_order=WorldSector.sort_order).execution_options(synchronize_session=False))
    return capital


def unlock_location(db, actor_id, *, location_id=None, key=None):
    lock_world(db)
    if key is not None:
        statement = select(WorldSector).where(WorldSector.key == key)
    elif location_id is not None:
        statement = select(WorldSector).where(WorldSector.location_id == location_id)
    else:
        locked = {row.key: row for row in db.scalars(select(WorldSector)
                  .where(WorldSector.location_id.is_not(None), WorldSector.unlocked.is_(False))
                  .execution_options(populate_existing=True))}
        ordered = sorted(map_config.by_key().values(), key=lambda row: row["unlock_order"])
        sector = next((locked[row["key"]] for row in ordered if row["key"] in locked), None)
    if key is not None or location_id is not None:
        sector = db.scalar(statement.execution_options(populate_existing=True))
    if sector is None:
        raise HTTPException(404 if key is not None or location_id is not None else 409,
                            "Сектор не знайдено." if key is not None or location_id is not None else "Усі локації вже відкрито.")
    if sector.unlocked:
        return sector, False
    opened = set(db.scalars(select(WorldSector.key).where(WorldSector.unlocked.is_(True))).all())
    legacy_origins = db.scalars(select(SectorConnection.origin).where(
        SectorConnection.destination == sector.key, SectorConnection.managed_by_config.is_(False),
    )).all()
    neighbor = opened.intersection(map_config.routes_from(sector.key)) or opened.intersection(legacy_origins)
    if not neighbor:
        raise HTTPException(409, "Локація має межувати з відкритою територією.")
    sector.unlocked = True
    sector.unlocked_at = utc_now()
    sector.unlocked_by = actor_id
    return sector, True


def close_location(db, location_id):
    capital = lock_world(db)
    if location_id == capital["id"]:
        raise HTTPException(409, "Стартовий сектор закрити неможливо.")
    sector = db.scalar(select(WorldSector).where(WorldSector.location_id == location_id)
                       .execution_options(populate_existing=True))
    if sector is None:
        raise HTTPException(404, "Сектор не знайдено.")
    if not sector.unlocked:
        return sector, False
    player = db.scalar(select(User.id).where(User.map_sector == sector.key).limit(1))
    journey = db.scalar(select(PlayerTravel.player_id).where(or_(
        PlayerTravel.origin == sector.key, PlayerTravel.destination == sector.key,
    )).limit(1))
    if player is not None or journey is not None:
        raise HTTPException(409, "У секторі є гравці або через нього триває подорож.")
    sector.unlocked = False
    sector.unlocked_at = None
    sector.unlocked_by = None
    return sector, True


def close_world_except_start(db):
    capital = lock_world(db)
    key = capital["key"]
    sector = db.get(WorldSector, key)
    if sector is None:
        raise RuntimeError("Стартовий сектор відсутній.")
    x, y = map_config.marker_position(key)
    # Lock travelers already at the capital before cancelling their journeys.
    db.execute(update(User).where(User.id.in_(select(PlayerTravel.player_id)))
               .values(map_sector=User.map_sector).execution_options(synchronize_session=False))
    journeys = db.execute(delete(PlayerTravel)).rowcount
    players = db.execute(update(User).where(User.map_sector != key)
                         .values(map_sector=key, map_x=x, map_y=y)).rowcount
    closed = db.execute(update(WorldSector).where(WorldSector.key != key, WorldSector.unlocked.is_(True))
                        .values(unlocked=False, unlocked_at=None, unlocked_by=None)).rowcount
    if not sector.unlocked:
        sector.unlocked = True
        sector.unlocked_at = utc_now()
    return {"closed": closed, "players": players, "journeys": journeys}


def administration_state(db):
    legacy = defaultdict(dict)
    for origin, destination, seconds in db.execute(select(
        SectorConnection.origin, SectorConnection.destination, SectorConnection.duration_seconds,
    ).where(SectorConnection.managed_by_config.is_(False))):
        legacy[origin][destination] = seconds
    rows = sectors(db)
    return {
        "config": map_config.config(),
        "status": [{
            "id": row.location_id, "unlocked": row.unlocked,
            "unlocked_at": utc_timestamp(row.unlocked_at) if row.unlocked_at else None,
            "unlocked_by": row.unlocked_by,
            "neighbors": {**map_config.routes_from(row.key), **legacy[row.key]},
        } for row in rows if row.location_id is not None],
        "open_keys": [row.key for row in rows if row.unlocked],
    }


def set_connection(db, origin, destination, duration_seconds, bidirectional):
    if origin == destination:
        raise HTTPException(422, "Обери різні сектори.")
    origin_row, destination_row = db.get(WorldSector, origin), db.get(WorldSector, destination)
    if origin_row is None or destination_row is None:
        raise HTTPException(404, "Сектор не знайдено.")
    if origin_row.location_id is not None and destination_row.location_id is not None:
        raise HTTPException(409, "Маршрути карти задаються в map_location.json.")
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

    present = location_available(db, player.map_sector)
    durations = routes_from(db, player.map_sector) if present else {}
    geography = map_config.config()
    visible = [sector for sector in sectors(db) if sector.unlocked]
    locations = map_config.by_key()
    fully_open = sum(sector.location_id is not None for sector in visible) == geography["map"]["total_locations"]
    enterprises = [] if journey or not location_available(db, player.map_sector, "enterprises") else db.scalars(
        select(Enterprise).where(Enterprise.sector == player.map_sector).order_by(Enterprise.id)
    ).all()
    return {
        "current_sector": player.map_sector,
        "map": geography["map"],
        "fog_of_war": {**geography["fog_of_war"], "enabled": geography["fog_of_war"]["enabled"] and not fully_open},
        "server_time": utc_timestamp(now),
        "work_blocks_travel": working_blocks_travel(db, player, now),
        "travel": {
            "origin": journey.origin, "destination": journey.destination,
            "waypoints": map_config.route_waypoints(journey.origin, journey.destination),
            "started_at": utc_timestamp(journey.started_at), "arrives_at": utc_timestamp(journey.arrives_at),
        } if journey else None,
        "sectors": [
            {
                "key": sector.key, "name": locations.get(sector.key, {}).get("name", sector.name), "unlocked": sector.unlocked,
                "map_x": sector.map_x, "map_y": sector.map_y,
                "duration_seconds": durations.get(sector.key),
                **{key: locations[sector.key][key] for key in ("id", "marker", "geometry", "description", "biome", "features")
                   if sector.key in locations},
            }
            for sector in visible
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
