"""Persist timed repair jobs, original durability and fractional guild progress."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_23"
down_revision = "20261124_22"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("items", sa.Column("initial_max_durability", sa.Integer()))
    op.execute("UPDATE items SET initial_max_durability = max_durability WHERE initial_max_durability IS NULL")
    with op.batch_alter_table("activity_guild_progress") as batch:
        batch.alter_column("points", existing_type=sa.Integer(), type_=sa.Numeric(16, 3), existing_nullable=False)
    op.create_table(
        "repair_jobs",
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(32), nullable=False),
        sa.Column("workshop", sa.String(32), nullable=False),
        sa.Column("ready_at", sa.DateTime(), nullable=False),
        sa.Column("gold", sa.Integer(), nullable=False),
        sa.Column("restored", sa.Integer(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
    )


def downgrade():
    op.drop_table("repair_jobs")
    with op.batch_alter_table("activity_guild_progress") as batch:
        batch.alter_column("points", existing_type=sa.Numeric(16, 3), type_=sa.Integer(), existing_nullable=False)
    with op.batch_alter_table("items") as batch:
        batch.drop_column("initial_max_durability")
