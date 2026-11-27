"""Link existing world sectors to the illustrated world and preserve their references."""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from backend.services.map_config import config

revision = "20261126_29"
down_revision = "20261125_28"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("world_sector_connections", sa.Column("managed_by_config", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("world_sectors", sa.Column("location_id", sa.Integer()))
    op.add_column("world_sectors", sa.Column("unlocked_at", sa.DateTime()))
    op.add_column("world_sectors", sa.Column("unlocked_by", sa.Integer()))
    op.create_index("ix_world_sectors_location_id", "world_sectors", ["location_id"], unique=True)

    db = op.get_bind()
    metadata = sa.MetaData()
    sectors, routes, users, enterprises, travels = (
        sa.Table(name, metadata, autoload_with=db) for name in (
            "world_sectors", "world_sector_connections", "users", "enterprises", "player_travel",
        )
    )
    old = {row.key: row for row in db.execute(sa.select(sectors))}
    source = config()
    rows = source["locations"]
    keys = {row["id"]: row["key"] for row in rows}
    established = (db.scalar(sa.select(sa.func.count()).select_from(users).where(users.c.is_system.is_(False)))
                   or db.scalar(sa.select(sa.func.count()).select_from(enterprises))
                   or db.scalar(sa.select(sa.func.count()).select_from(travels))
                   or set(old) - source["legacy_mapping"].keys())
    occupied = set(db.scalars(sa.select(users.c.map_sector))) | set(db.scalars(sa.select(enterprises.c.sector)))
    for origin, destination in db.execute(sa.select(travels.c.origin, travels.c.destination)):
        occupied.update((origin, destination))
    now = datetime.now(UTC).replace(tzinfo=None)
    for row in rows:
        key = row["key"]
        existing = old.get(key)
        if existing is not None and source["legacy_mapping"].get(key) != row["id"] and existing.name != row["name"]:
            raise RuntimeError(f"Map location key {key!r} conflicts with an existing sector. Resolve the mapping first.")
        opened = row["unlocked_by_default"] or key in occupied or bool(established and existing and existing.unlocked)
        values = {
            "location_id": row["id"], "name": row["name"], "unlocked": opened,
            "unlocked_at": now if opened else None, "sort_order": row["unlock_order"],
            "map_x": round(100 * row["marker"]["x"]), "map_y": round(100 * row["marker"]["y"]),
        }
        if existing is None:
            db.execute(sectors.insert().values(key=key, **values))
        else:
            db.execute(sectors.update().where(sectors.c.key == key).values(**values))
        db.execute(users.update().where(users.c.map_sector == key)
                   .values(map_x=values["map_x"], map_y=values["map_y"]))

    for key in occupied - set(keys.values()):
        if key in old and not old[key].unlocked:
            db.execute(sectors.update().where(sectors.c.key == key).values(unlocked=True, unlocked_at=now))

    old_routes = {(row.origin, row.destination): row.duration_seconds for row in db.execute(sa.select(routes))}
    for row in rows:
        for route in row["connections"]:
            origin, destination = row["key"], keys[route["location_id"]]
            pair = origin, destination
            reverse = destination, origin
            default = route["travel_time_seconds"]
            if pair not in old_routes:
                db.execute(routes.insert().values(
                    origin=origin, destination=destination,
                    duration_seconds=old_routes.get(reverse, default),
                    managed_by_config=old_routes.get(reverse, default) == default,
                ))
            elif old_routes[pair] == default and old_routes.get(reverse, default) == default:
                db.execute(routes.update().where(routes.c.origin == origin, routes.c.destination == destination)
                           .values(managed_by_config=True))


def downgrade():
    # Keep added sectors and routes because journeys and enterprises may already reference them.
    op.drop_column("world_sector_connections", "managed_by_config")
    op.drop_index("ix_world_sectors_location_id", table_name="world_sectors")
    op.drop_column("world_sectors", "unlocked_by")
    op.drop_column("world_sectors", "unlocked_at")
    op.drop_column("world_sectors", "location_id")
