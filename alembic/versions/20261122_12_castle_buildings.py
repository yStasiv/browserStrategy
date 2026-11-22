"""Store completed castle buildings."""

import sqlalchemy as sa
from alembic import op

revision = "20261122_12"
down_revision = "20261122_11"
branch_labels = None
depends_on = None


def upgrade():
    # The development server may have created this table during a reload.
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table("castle_buildings"):
        return
    op.create_table(
        "castle_buildings",
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("building_id", sa.String(64), primary_key=True),
    )


def downgrade():
    op.drop_table("castle_buildings")
