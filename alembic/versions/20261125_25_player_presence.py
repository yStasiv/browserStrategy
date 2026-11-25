"""Track recent player presence."""

import sqlalchemy as sa
from alembic import op

revision = "20261125_25"
down_revision = "20261124_24"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"])


def downgrade():
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.drop_column("users", "last_seen_at")
