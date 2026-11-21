"""Rename the two existing resource balances and objective identifiers."""

from alembic import op
import sqlalchemy as sa

revision = "20261120_08"
down_revision = "20261120_07"
branch_labels = None
depends_on = None

RENAMES = (("wood", "singing_resin"), ("stone", "basalt_bone"))


def rename(pairs, reserved):
    db = op.get_bind()
    for old, new in pairs:
        op.alter_column("users", old, new_column_name=new, existing_type=sa.Integer())
        db.execute(sa.text("UPDATE enterprises SET resource_type = :new WHERE resource_type = :old"),
                   {"old": old, "new": new})
        for table in ("guild_quest_templates", "guild_quest_instances"):
            db.execute(sa.text(f"UPDATE {table} SET resource = :new WHERE resource = :old"),
                       {"old": old, "new": new})
    with op.batch_alter_table("player_resource_balances") as batch:
        batch.drop_constraint("ck_player_resource_nonlegacy", type_="check")
        batch.create_check_constraint("ck_player_resource_nonlegacy", reserved)


def upgrade():
    rename(RENAMES, "resource_id NOT IN ('gold', 'wood', 'stone', 'singing_resin', 'basalt_bone')")


def downgrade():
    rename([(new, old) for old, new in RENAMES], "resource_id NOT IN ('gold', 'wood', 'stone')")
