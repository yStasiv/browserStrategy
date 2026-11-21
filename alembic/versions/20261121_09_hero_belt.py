"""Add the hero's belt slot."""

import sqlalchemy as sa
from alembic import op

revision = "20261121_09"
down_revision = "20261120_08"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("equipped_items") as batch:
        batch.add_column(sa.Column("belt_id", sa.Integer(), sa.ForeignKey("items.id", name="fk_equipped_belt_item")))


def downgrade():
    with op.batch_alter_table("equipped_items") as batch:
        batch.drop_constraint("fk_equipped_belt_item", type_="foreignkey")
        batch.drop_column("belt_id")
