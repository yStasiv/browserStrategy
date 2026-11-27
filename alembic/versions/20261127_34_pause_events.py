"""Persist paused event state without discarding contributions."""
from alembic import op
import sqlalchemy as sa

revision = "20261127_34"
down_revision = "20261127_33"
branch_labels = None
depends_on = None

STATUSES = "'DRAFT','ACTIVE','COMPLETED','REWARDED','CANCELLED'"


def upgrade():
    with op.batch_alter_table("global_events") as batch:
        batch.drop_constraint("ck_global_event_status", type_="check")
        batch.create_check_constraint("ck_global_event_status", f"status IN ({STATUSES},'PAUSED')")
        batch.add_column(sa.Column("paused_at", sa.DateTime()))


def downgrade():
    with op.batch_alter_table("global_events") as batch:
        batch.drop_constraint("ck_global_event_status", type_="check")
        batch.create_check_constraint("ck_global_event_status", f"status IN ({STATUSES})")
        batch.drop_column("paused_at")
