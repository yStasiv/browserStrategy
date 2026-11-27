"""Allow multiple mines of one type and persist each mine's opening balance."""
from alembic import op
import sqlalchemy as sa

revision = "20261127_33"
down_revision = "20261127_32"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("event_constructions") as batch:
        batch.drop_constraint("uq_event_construction_type", type_="unique")
        batch.add_column(sa.Column("opening_balance", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("event_constructions") as batch:
        batch.create_unique_constraint("uq_event_construction_type", ["event_id", "enterprise_type"])
        batch.drop_column("opening_balance")
