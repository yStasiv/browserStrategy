"""Persist construction events, contribution and reward ledgers."""
from alembic import op
import sqlalchemy as sa

revision = "20261127_32"
down_revision = "20261127_31"
branch_labels = None
depends_on = None


def fk(name, target, **options):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(target), **options)


def upgrade():
    op.create_table(
        "global_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rules", sa.Text(), nullable=False),
        sa.Column("completion", sa.Text(), nullable=False),
        sa.Column("reward_description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(), sa.ForeignKey("world_sectors.key"), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        fk("created_by", "users.id", nullable=False),
        sa.Column("started_at", sa.DateTime()),
        fk("started_by", "users.id"),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("rewarded_at", sa.DateTime()),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','COMPLETED','REWARDED','CANCELLED')",
                           name="ck_global_event_status"),
    )
    op.create_index("ix_global_events_status", "global_events", ["status"])
    op.create_table(
        "event_constructions",
        sa.Column("id", sa.Integer(), primary_key=True),
        fk("event_id", "global_events.id", nullable=False),
        fk("enterprise_id", "enterprises.id", unique=True),
        sa.Column("enterprise_type", sa.String(64), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=False),
        sa.Column("collected", sa.JSON(), nullable=False),
        sa.Column("stage_images", sa.JSON(), nullable=False),
        sa.Column("construction_started_at", sa.DateTime()),
        sa.Column("frame_completed_at", sa.DateTime()),
        sa.Column("construction_completed_at", sa.DateTime()),
        sa.Column("operational_since", sa.DateTime()),
        sa.UniqueConstraint("event_id", "enterprise_type", name="uq_event_construction_type"),
    )
    op.create_index("ix_event_constructions_construction_completed_at", "event_constructions",
                    ["construction_completed_at"])
    op.create_table(
        "construction_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        fk("event_id", "global_events.id", nullable=False),
        fk("enterprise_id", "enterprises.id", nullable=False),
        fk("player_id", "users.id", nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("player_id", "operation_id", name="uq_construction_operation"),
        sa.CheckConstraint("quantity > 0 AND unit_price >= 0", name="ck_construction_contribution_amount"),
    )
    op.create_index("ix_construction_contributions_event_id", "construction_contributions", ["event_id"])
    op.create_index("ix_construction_contributions_enterprise_id", "construction_contributions", ["enterprise_id"])
    op.create_table(
        "event_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        fk("event_id", "global_events.id", nullable=False),
        fk("player_id", "users.id", nullable=False),
        sa.Column("operation_id", sa.String(36), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("multiplier", sa.String(20), nullable=False),
        fk("administrator_id", "users.id", nullable=False),
        fk("issued_by", "users.id"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("issued_at", sa.DateTime()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.UniqueConstraint("event_id", "player_id", name="uq_event_reward_player"),
        sa.CheckConstraint("status IN ('PENDING','PROCESSING','ISSUED','FAILED')",
                           name="ck_event_reward_status"),
    )
    op.create_table(
        "global_event_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        fk("event_id", "global_events.id", nullable=False),
        fk("administrator_id", "users.id", nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_global_event_audit_event_id", "global_event_audit", ["event_id"])
    with op.batch_alter_table("news") as batch:
        batch.add_column(sa.Column("event_id", sa.Integer()))
        batch.add_column(sa.Column("recipient_id", sa.Integer()))
        batch.create_foreign_key("fk_news_event", "global_events", ["event_id"], ["id"])
        batch.create_foreign_key("fk_news_recipient", "users", ["recipient_id"], ["id"])
        batch.create_index("ix_news_event_id", ["event_id"])
        batch.create_index("ix_news_recipient_id", ["recipient_id"])


def downgrade():
    op.execute(sa.text("DELETE FROM news_acknowledgments WHERE news_id IN (SELECT id FROM news WHERE event_id IS NOT NULL)"))
    op.execute(sa.text("DELETE FROM news WHERE event_id IS NOT NULL"))
    with op.batch_alter_table("news") as batch:
        batch.drop_index("ix_news_event_id")
        batch.drop_index("ix_news_recipient_id")
        batch.drop_constraint("fk_news_recipient", type_="foreignkey")
        batch.drop_constraint("fk_news_event", type_="foreignkey")
        batch.drop_column("recipient_id")
        batch.drop_column("event_id")
    for table in ("global_event_audit", "event_rewards", "construction_contributions",
                  "event_constructions", "global_events"):
        op.drop_table(table)
