"""Store additional resource prices for artifact listings."""

from alembic import op
import sqlalchemy as sa

revision = "20261123_20"
down_revision = "20261123_19"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shop_items", sa.Column("resource_costs", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    with op.batch_alter_table("shop_items") as batch:
        batch.drop_column("resource_costs")
