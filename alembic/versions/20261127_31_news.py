"""Persist news drafts, releases and individual acknowledgments."""
from alembic import op
import sqlalchemy as sa

revision = "20261127_31"
down_revision = "20261126_30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(255)),
        sa.Column("link_url", sa.String(2048)),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.CheckConstraint("(status = 'draft' AND published_at IS NULL) OR "
                           "(status = 'published' AND published_at IS NOT NULL)", name="ck_news_publication"),
    )
    op.create_index("ix_news_publication", "news", ["status", "published_at", "id"])
    op.create_table(
        "news_acknowledgments",
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("news_id", sa.Integer(), sa.ForeignKey("news.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade():
    op.drop_table("news_acknowledgments")
    op.drop_table("news")
