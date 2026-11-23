"""Summarize enterprise history daily and decouple administration from faction."""

from datetime import timezone
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "20261123_16"
down_revision = "20261122_15"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("enterprise_shifts", sa.Column("enterprise_payable", sa.Integer()))
    reports = op.create_table(
        "enterprise_daily_reports",
        sa.Column("enterprise_id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("produced", sa.JSON(), nullable=False),
        sa.Column("sold", sa.JSON(), nullable=False),
        sa.Column("sale_gold", sa.BigInteger(), nullable=False),
        sa.Column("wages", sa.BigInteger(), nullable=False),
    )

    events = sa.table(
        "enterprise_events", sa.column("enterprise_id"), sa.column("kind"),
        sa.column("created_at", sa.DateTime()), sa.column("details", sa.JSON()),
    )
    connection = op.get_bind()
    kyiv = ZoneInfo("Europe/Kyiv")
    totals = {}
    for event in connection.execute(sa.select(events).where(events.c.kind.in_(("production", "sale", "settlement")))):
        day = event.created_at.replace(tzinfo=timezone.utc).astimezone(kyiv).date()
        key = (event.enterprise_id, day)
        report = totals.setdefault(key, dict(
            enterprise_id=event.enterprise_id, day=day, produced={}, sold={}, sale_gold=0, wages=0,
        ))
        if event.kind == "settlement":
            report["wages"] += event.details["wage"]
        else:
            amounts = report["produced" if event.kind == "production" else "sold"]
            resource = event.details["resource"]
            amounts[resource] = amounts.get(resource, 0) + event.details["quantity"]
            if event.kind == "sale":
                report["sale_gold"] += event.details["subtotal"]
    if totals:
        connection.execute(reports.insert(), list(totals.values()))

    for building in ("elves_recruitment_tier_1", "elves_recruitment_tier_2"):
        connection.execute(sa.text("""
            INSERT INTO castle_buildings (player_id, building_id)
            SELECT users.id, :building FROM users
            WHERE (lower(trim(users.fraction)) IN ('admin', 'administration', 'адміністрація')
                   OR trim(users.fraction) = 'Адміністрація')
            AND NOT EXISTS (
                SELECT 1 FROM castle_buildings WHERE player_id = users.id AND building_id = :building
            )
        """), {"building": building})
    # SQLite LOWER is ASCII-only, so include the legacy display label explicitly.
    op.execute("""
        UPDATE users SET fraction = 'elfe'
        WHERE lower(trim(fraction)) IN ('admin', 'administration', 'адміністрація') OR trim(fraction) = 'Адміністрація'
    """)
    op.execute("UPDATE users SET is_admin = true WHERE id = 5")


def downgrade():
    # Keep faction and permission changes, which may have been edited since the migration.
    op.drop_table("enterprise_daily_reports")
    with op.batch_alter_table("enterprise_shifts") as batch:
        batch.drop_column("enterprise_payable")
