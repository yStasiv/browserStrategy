"""Keep the former login name while a replacement nickname is required."""
import sqlalchemy as sa
from alembic import op

revision = "20261125_28"
down_revision = "20261125_27"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("nickname_reset_from", sa.String()))
    op.create_index("ix_users_nickname_reset_from", "users", ["nickname_reset_from"], unique=True)


def downgrade():
    op.execute("UPDATE users SET username = nickname_reset_from WHERE nickname_reset_from IS NOT NULL")
    op.drop_index("ix_users_nickname_reset_from", table_name="users")
    op.drop_column("users", "nickname_reset_from")
