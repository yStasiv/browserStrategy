"""Track level-up attribute allocations separately from other bonuses."""

import sqlalchemy as sa
from alembic import op

revision = "20261122_10"
down_revision = "20261121_09"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("attribute_allocations", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.execute(
        "UPDATE users SET pending_attribute_points = COALESCE(pending_attribute_points, 0) + 1 "
        "WHERE level = 8"
    )


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("attribute_allocations")
