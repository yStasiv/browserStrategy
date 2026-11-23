"""Keep purchased equipment level requirements and move legacy bows to off hand."""

from alembic import op
import sqlalchemy as sa

revision = "20261124_21"
down_revision = "20261123_20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("items", sa.Column("level_required", sa.Integer(), nullable=False, server_default="1"))
    op.execute("""
        UPDATE items
        SET level_required = COALESCE((
            SELECT MIN(shop_items.level_required)
            FROM shop_items JOIN items AS template ON template.id = shop_items.item_template_id
            WHERE template.name = items.name AND template.item_type = items.item_type
        ), 1)
    """)
    op.execute("""
        UPDATE equipped_items SET left_hand_id = right_hand_id, right_hand_id = NULL
        WHERE left_hand_id IS NULL AND right_hand_id IN (SELECT id FROM items WHERE item_type = 'bow')
    """)


def downgrade():
    with op.batch_alter_table("items") as batch:
        batch.drop_column("level_required")
