"""Record shop purchases, repairs and item breakage for admin statistics."""
import sqlalchemy as sa
from alembic import context, op

revision = "20261125_26"
down_revision = "20261125_25"
branch_labels = None
depends_on = None


def upgrade():
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    table = "gameplay_events"
    index = "ix_gameplay_events_occurred_at"
    if inspector is None or not inspector.has_table(table):
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
        )
        op.create_index(index, table, ["occurred_at"])
    elif not any(row["name"] == index for row in inspector.get_indexes(table)):
        op.create_index(index, table, ["occurred_at"])


def downgrade():
    op.drop_table("gameplay_events")
