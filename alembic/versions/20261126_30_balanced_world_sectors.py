"""Refresh geographic markers and managed routes while retaining sector identities."""
import sqlalchemy as sa
from alembic import op

from backend.services.map_config import by_key, marker_position, routes_from

revision = "20261126_30"
down_revision = "20261126_29"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    metadata = sa.MetaData()
    sectors, users, routes = [sa.Table(name, metadata, autoload_with=db) for name in (
        "world_sectors", "users", "world_sector_connections",
    )]
    configured = by_key()
    identities = dict(db.execute(sa.select(sectors.c.key, sectors.c.location_id)).all())
    for key, row in configured.items():
        if identities.get(key) != row["id"]:
            raise RuntimeError(f"Resolve sector identity for {key!r} before replacing world geography.")

    existing = {(row.origin, row.destination): row for row in db.execute(sa.select(routes))}
    for (origin, destination), route in existing.items():
        if origin in configured and destination in configured and destination not in routes_from(origin):
            if not route.managed_by_config:
                raise RuntimeError(f"Legacy route {origin!r} → {destination!r} no longer joins adjacent sectors.")

    for key, row in configured.items():
        x, y = marker_position(key)
        db.execute(sectors.update().where(sectors.c.key == key).values(
            map_x=x, map_y=y, name=row["name"], sort_order=row["unlock_order"],
        ))
        db.execute(users.update().where(users.c.map_sector == key).values(map_x=x, map_y=y))
        for destination, duration in routes_from(key).items():
            current = existing.get((key, destination))
            if current is None:
                db.execute(routes.insert().values(origin=key, destination=destination,
                    duration_seconds=duration, managed_by_config=True))
            elif current.managed_by_config and current.duration_seconds != duration:
                db.execute(routes.update().where(routes.c.origin == key, routes.c.destination == destination)
                           .values(duration_seconds=duration))
    for (origin, destination), route in existing.items():
        if origin in configured and route.managed_by_config and destination not in routes_from(origin):
            db.execute(routes.delete().where(routes.c.origin == origin, routes.c.destination == destination))


def downgrade():
    # Data-only revision. Keep migrated identifiers, marker positions and active journeys.
    pass
