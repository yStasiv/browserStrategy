"""Persist enterprise shifts, inventory inputs and the operation journal."""

import sqlalchemy as sa
from alembic import op

revision = "20261122_15"
down_revision = "20261122_14"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("enterprises")}
    if "input_stock" not in columns:
        op.add_column("enterprises", sa.Column("input_stock", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if "production_remainder" not in columns:
        op.add_column("enterprises", sa.Column("production_remainder", sa.Integer(), nullable=False, server_default="0"))
    # Local development may have bootstrapped these models before Alembic ran.
    if not inspector.has_table("enterprise_shifts"):
        op.create_table(
            "enterprise_shifts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("enterprise_id", sa.Integer(), nullable=False),
            sa.Column("worker_id", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completes_at", sa.DateTime(), nullable=False),
            sa.Column("settled_at", sa.DateTime()),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("base_wage", sa.Integer(), nullable=False),
            sa.Column("multiplier_percent", sa.Integer(), nullable=False),
            sa.Column("penalty_percent", sa.Integer(), nullable=False),
            sa.Column("payable", sa.Integer(), nullable=False),
        )
        op.create_index("ix_enterprise_shifts_worker_status", "enterprise_shifts", ["worker_id", "status"])
    if not inspector.has_table("enterprise_events"):
        op.create_table(
            "enterprise_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("enterprise_id", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Integer()),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("request_key", sa.String(36), unique=True),
        )
        op.create_index("ix_enterprise_events_history", "enterprise_events", ["enterprise_id", "id"])


def downgrade():
    op.drop_table("enterprise_events")
    op.drop_table("enterprise_shifts")
    with op.batch_alter_table("enterprises") as batch:
        batch.drop_column("production_remainder")
        batch.drop_column("input_stock")
