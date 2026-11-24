"""Persist the effective levels of existing activity guilds."""

import sqlalchemy as sa
from alembic import op

from backend.services.activity_guilds import level_limits
from backend.services.guild_experience import xp_threshold

revision = "20261124_24"
down_revision = "20261124_23"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("activity_guild_progress", sa.Column("level", sa.Integer()))
    progress = sa.table(
        "activity_guild_progress",
        sa.column("player_id"), sa.column("guild"), sa.column("points"), sa.column("level"),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(progress)).all():
        level, max_level = level_limits(row.guild)
        points = row.points
        while level != max_level:
            threshold = xp_threshold(level, row.guild)
            if points < threshold:
                break
            points -= threshold
            level += 1
        connection.execute(
            progress.update()
            .where(progress.c.player_id == row.player_id, progress.c.guild == row.guild)
            .values(level=level)
        )


def downgrade():
    op.drop_column("activity_guild_progress", "level")
