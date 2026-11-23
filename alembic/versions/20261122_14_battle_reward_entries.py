"""Record extensible display entries alongside battle reward transactions."""

import sqlalchemy as sa
from alembic import op

revision = "20261122_14"
down_revision = "20261122_13"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reward_transactions", sa.Column("reward_entries", sa.JSON(none_as_null=True), nullable=True))


def downgrade():
    with op.batch_alter_table("reward_transactions") as batch:
        batch.drop_column("reward_entries")
