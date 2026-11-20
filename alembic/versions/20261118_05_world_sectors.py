"""Persist world sectors, connections and active journeys."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_05"
down_revision = "20261118_04"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    old_keys = connection.execute(sa.text(
        "SELECT map_sector AS key FROM users UNION SELECT sector FROM enterprises"
    )).scalars().all()
    if any(key is None or not key.strip() for key in old_keys):
        raise RuntimeError("Resolve empty sector keys before applying the world sector migration.")

    sectors = op.create_table(
        "world_sectors",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("unlocked", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("map_x", sa.Integer()),
        sa.Column("map_y", sa.Integer()),
        sa.CheckConstraint(
            "(map_x IS NULL AND map_y IS NULL) OR "
            "(map_x IS NOT NULL AND map_y IS NOT NULL AND map_x BETWEEN 0 AND 100 AND map_y BETWEEN 0 AND 100)",
            name="ck_world_sector_map_position",
        ),
    )
    initial = [
        ("Mountain", "Гори", 17),
        ("Castle", "Замок", 50),
        ("Forest", "Ліс", 83),
    ]
    rows = [
        dict(key=key, name=name, unlocked=True, sort_order=order, map_x=x, map_y=50)
        for order, (key, name, x) in enumerate(initial)
    ]
    extra_keys = sorted(set(old_keys) - {key for key, _, _ in initial})
    rows.extend(
        dict(key=key, name=key, unlocked=False, sort_order=order, map_x=None, map_y=None)
        for order, key in enumerate(extra_keys, start=len(rows))
    )
    op.bulk_insert(sectors, rows)

    connections = op.create_table(
        "world_sector_connections",
        sa.Column("origin", sa.String(), sa.ForeignKey("world_sectors.key"), primary_key=True),
        sa.Column("destination", sa.String(), sa.ForeignKey("world_sectors.key"), primary_key=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.CheckConstraint("origin != destination", name="ck_world_distinct_sectors"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_world_positive_duration"),
    )
    op.bulk_insert(connections, [
        dict(origin="Mountain", destination="Castle", duration_seconds=2),
        dict(origin="Castle", destination="Mountain", duration_seconds=2),
        dict(origin="Castle", destination="Forest", duration_seconds=4),
        dict(origin="Forest", destination="Castle", duration_seconds=4),
    ])

    with op.batch_alter_table("users") as batch:
        batch.alter_column("map_sector", existing_type=sa.String(), nullable=False)
        batch.create_foreign_key("fk_users_map_sector", "world_sectors", ["map_sector"], ["key"])
    with op.batch_alter_table("enterprises") as batch:
        batch.alter_column("sector", existing_type=sa.String(), nullable=False)
        batch.create_foreign_key("fk_enterprises_sector", "world_sectors", ["sector"], ["key"])

    op.create_table(
        "player_travel",
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("origin", sa.String(), sa.ForeignKey("world_sectors.key"), nullable=False),
        sa.Column("destination", sa.String(), sa.ForeignKey("world_sectors.key"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("arrives_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("origin != destination", name="ck_travel_distinct_sectors"),
        sa.CheckConstraint("arrives_at > started_at", name="ck_travel_positive_duration"),
    )


def downgrade():
    op.drop_table("player_travel")
    with op.batch_alter_table("enterprises") as batch:
        batch.drop_constraint("fk_enterprises_sector", type_="foreignkey")
        batch.alter_column("sector", existing_type=sa.String(), nullable=True)
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_map_sector", type_="foreignkey")
        batch.alter_column("map_sector", existing_type=sa.String(), nullable=True)
    op.drop_table("world_sector_connections")
    op.drop_table("world_sectors")
