"""Record hero gender and default existing characters to male."""

import sqlalchemy as sa
from alembic import op

revision = "20261123_19"
down_revision = "20261123_18"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column(
        "gender", sa.String(6), sa.CheckConstraint("gender IN ('male', 'female')", name="ck_users_gender"),
        nullable=False, server_default="male",
    ))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_gender", type_="check")
        batch.drop_column("gender")
