"""Store moderator roles and account moderation history."""
import sqlalchemy as sa
from alembic import op

revision = "20261125_27"
down_revision = "20261125_26"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_moderator", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("ban_reason", sa.String(500), nullable=True))
    op.create_table(
        "player_moderation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_player_moderation_events_player_id", "player_moderation_events", ["player_id"])


def downgrade():
    op.drop_table("player_moderation_events")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "is_moderator")
