"""Classify the current enterprises as mines."""

from alembic import op

revision = "20261123_17"
down_revision = "20261123_16"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE enterprises SET production_type = 'mine' WHERE production_type IS NULL OR production_type <> 'mine'")


def downgrade():
    # Original types can be recovered from the pre-migration database backup.
    pass
