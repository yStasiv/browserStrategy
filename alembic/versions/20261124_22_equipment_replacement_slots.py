"""Remember the last replacement slot for equipment types with multiple slots."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_22"
down_revision = "20261124_21"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("equipped_items", sa.Column(
        "replacement_slots", sa.JSON(), nullable=False, server_default=sa.text("'{}'"),
    ))


def downgrade():
    with op.batch_alter_table("equipped_items") as batch:
        batch.drop_column("replacement_slots")
