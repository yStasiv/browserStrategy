"""Resolve enterprise ownership from the system role instead of a fixed ID."""
from alembic import op

revision = "20261127_35"
down_revision = "20261127_34"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("enterprises") as batch:
        batch.alter_column("owner_id", server_default=None)


def downgrade():
    with op.batch_alter_table("enterprises") as batch:
        batch.alter_column("owner_id", server_default="1")
