"""Add Adventurers Guild progression."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_02'
down_revision = '20261118_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('guild_quest_templates',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('resource', sa.String(length=32), nullable=False),
        sa.Column('difficulty', sa.String(length=32), nullable=False),
        sa.Column('min_level', sa.Integer(), nullable=False),
        sa.Column('required', sa.Integer(), nullable=False),
        sa.Column('gold', sa.Integer(), nullable=False),
        sa.Column('wood', sa.Integer(), nullable=False),
        sa.Column('stone', sa.Integer(), nullable=False),
        sa.Column('xp', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )
    op.create_table('guild_processed_events',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('player_id', 'event_type', 'source_id')
    )
    op.create_table('guild_progress',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('xp', sa.Integer(), nullable=False),
        sa.Column('next_xp', sa.Integer(), nullable=False),
        sa.Column('claimed_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['player_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('player_id')
    )
    op.create_table('guild_daily_replacements',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('utc_date', sa.Date(), nullable=False),
        sa.Column('used', sa.Integer(), nullable=False),
        sa.CheckConstraint('used BETWEEN 0 AND 3'),
        sa.ForeignKeyConstraint(['player_id'], ['guild_progress.player_id'], ),
        sa.PrimaryKeyConstraint('player_id', 'utc_date')
    )
    op.create_table('guild_quest_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('template_key', sa.String(length=64), nullable=False),
        sa.Column('generation_level', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('resource', sa.String(length=32), nullable=False),
        sa.Column('difficulty', sa.String(length=32), nullable=False),
        sa.Column('required', sa.Integer(), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('gold', sa.Integer(), nullable=False),
        sa.Column('wood', sa.Integer(), nullable=False),
        sa.Column('stone', sa.Integer(), nullable=False),
        sa.Column('xp', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('available', 'in_progress', 'completed', 'reward_claimed', 'replaced')"),
        sa.CheckConstraint('progress >= 0 AND progress <= required AND required > 0'),
        sa.ForeignKeyConstraint(['player_id'], ['guild_progress.player_id'], ),
        sa.ForeignKeyConstraint(['template_key'], ['guild_quest_templates.key'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'id')
    )
    op.create_table('guild_quest_slots',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('quest_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('number BETWEEN 1 AND 5'),
        sa.ForeignKeyConstraint(['player_id', 'quest_id'], ['guild_quest_instances.player_id', 'guild_quest_instances.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['guild_progress.player_id'], ),
        sa.PrimaryKeyConstraint('player_id', 'number'),
        sa.UniqueConstraint('quest_id')
    )
    templates = sa.table(
        "guild_quest_templates", sa.column("key", sa.String()), sa.column("title", sa.String()),
        sa.column("category", sa.String()), sa.column("resource", sa.String()), sa.column("difficulty", sa.String()),
        sa.column("min_level", sa.Integer()), sa.column("required", sa.Integer()), sa.column("gold", sa.Integer()),
        sa.column("wood", sa.Integer()), sa.column("stone", sa.Integer()), sa.column("xp", sa.Integer()), sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(templates, [
        dict(key=key, title=title, category="collection", resource=resource,
             difficulty=difficulty, min_level=level, required=required,
             gold=gold, wood=wood, stone=stone, xp=xp, enabled=True)
        for key, title, resource, difficulty, level, required, gold, wood, stone, xp in [
            ("wood_supply", "Запас деревини", "wood", "Легкий", 1, 3, 12, 0, 0, 30),
            ("stone_supply", "Запас каменю", "stone", "Легкий", 1, 3, 12, 0, 0, 30),
            ("wood_workshop", "Деревина для майстерні", "wood", "Звичайний", 1, 5, 22, 0, 1, 45),
            ("stone_masons", "Камінь для мулярів", "stone", "Звичайний", 1, 5, 22, 1, 0, 45),
            ("wood_warehouse", "Поповнення складу", "wood", "Звичайний", 1, 7, 32, 0, 2, 55),
            ("stone_fortification", "Запаси для укріплень", "stone", "Складний", 2, 10, 50, 2, 0, 75),
        ]
    ])



def downgrade():
    op.drop_table('guild_quest_slots')
    op.drop_table('guild_quest_instances')
    op.drop_table('guild_daily_replacements')
    op.drop_table('guild_progress')
    op.drop_table('guild_processed_events')
    op.drop_table('guild_quest_templates')
