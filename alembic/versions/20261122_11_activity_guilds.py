"""Track progress for activity-based guilds."""

import sqlalchemy as sa
from alembic import op

revision = "20261122_11"
down_revision = "20261122_10"
branch_labels = None
depends_on = None


def upgrade():
    # A running development server may have created this table before the migration.
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table("activity_guild_progress"):
        return
    op.create_table(
        "activity_guild_progress",
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("guild", sa.String(32), primary_key=True),
        sa.Column("points", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("activity_guild_progress")
