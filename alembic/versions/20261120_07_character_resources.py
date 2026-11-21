"""Store additional character resources without duplicating legacy balances."""

import sqlalchemy as sa
from alembic import op

revision = "20261120_07"
down_revision = "20261120_06"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "player_resource_balances",
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("resource_id", sa.String(64), primary_key=True),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_player_resource_quantity"),
        sa.CheckConstraint("resource_id NOT IN ('gold', 'wood', 'stone')", name="ck_player_resource_nonlegacy"),
    )


def downgrade():
    op.drop_table("player_resource_balances")
