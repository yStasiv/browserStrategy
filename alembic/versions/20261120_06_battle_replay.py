"""Persist replay checkpoints and versioned events."""

import sqlalchemy as sa
from alembic import op

revision = "20261120_06"
down_revision = "20261118_05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("battles", sa.Column("initial_state", sa.JSON(none_as_null=True)))
    op.add_column("battles", sa.Column("replay_schema_version", sa.Integer()))
    op.add_column("battle_actions", sa.Column("replay_events", sa.JSON(none_as_null=True)))


def downgrade():
    op.drop_column("battle_actions", "replay_events")
    op.drop_column("battles", "replay_schema_version")
    op.drop_column("battles", "initial_state")
