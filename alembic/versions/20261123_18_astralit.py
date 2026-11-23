"""Rename the conditional resource to astralit without losing balances."""

import sqlalchemy as sa
from alembic import op

revision = "20261123_18"
down_revision = "20261123_17"
branch_labels = None
depends_on = None


def rename(old, new):
    db = op.get_bind()
    params = {"old": old, "new": new}
    db.execute(sa.text("""
        INSERT INTO player_resource_balances (player_id, resource_id, quantity)
        SELECT player_id, :new, quantity FROM player_resource_balances WHERE resource_id = :old
        ON CONFLICT (player_id, resource_id) DO UPDATE
        SET quantity = player_resource_balances.quantity + excluded.quantity
    """), params)
    db.execute(sa.text("DELETE FROM player_resource_balances WHERE resource_id = :old"), params)

    for table_name, column in (("enterprises", "resource_type"), ("guild_quest_templates", "resource"),
                               ("guild_quest_instances", "resource")):
        db.execute(sa.text(f"UPDATE {table_name} SET {column} = :new WHERE {column} = :old"), params)

    def rename_amount(amounts):
        if old in amounts:
            amounts[new] = amounts.get(new, 0) + amounts.pop(old)

    for table_name, columns in (("enterprises", ("input_stock",)),
                                ("enterprise_daily_reports", ("produced", "sold")),
                                ("enterprise_events", ("details",))):
        table = sa.Table(table_name, sa.MetaData(), autoload_with=db)
        primary_key = list(table.primary_key)
        fields = [table.c[name] for name in columns]
        query = sa.select(*primary_key, *fields).where(sa.or_(*(
            field.cast(sa.String).contains(old, autoescape=True) for field in fields
        )))
        for row in db.execute(query).mappings().all():
            updates = {}
            for field in fields:
                data = row[field.name]
                if data and field.name == "details":
                    if data.get("resource") == old:
                        data["resource"] = new
                    rename_amount(data.get("inputs", {}))
                elif data:
                    rename_amount(data)
                updates[field.name] = data
            db.execute(table.update().where(*(column == row[column.name] for column in primary_key)).values(**updates))


def upgrade():
    rename("reserved_resource_7", "astralit")


def downgrade():
    rename("astralit", "reserved_resource_7")
