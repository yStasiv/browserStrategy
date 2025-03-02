"""Add quest scenarios

Revision ID: add_quest_scenarios
Revises: add_avatar_url_column
Create Date: 2024-03-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_quest_scenarios'
down_revision = 'add_avatar_url_column'
branch_labels = None
depends_on = None

def upgrade():
    # Створюємо таблицю quest_scenarios
    op.create_table(
        'quest_scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('min_level', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Додаємо нові колонки до таблиці tasks
    op.add_column('tasks', sa.Column('scenario_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('order_in_scenario', sa.Integer(), nullable=True, server_default='0'))
    
    # Створюємо зовнішній ключ
    op.create_foreign_key(
        'fk_task_scenario',
        'tasks', 'quest_scenarios',
        ['scenario_id'], ['id']
    )
    
    # Видаляємо старі колонки з таблиці tasks
    op.drop_column('tasks', 'is_completed')
    
    # Оновлюємо level_required
    op.execute('ALTER TABLE tasks ALTER COLUMN level_required SET DEFAULT 1')
    op.execute('UPDATE tasks SET level_required = 1 WHERE level_required IS NULL')

def downgrade():
    # Видаляємо зовнішній ключ
    op.drop_constraint('fk_task_scenario', 'tasks', type_='foreignkey')
    
    # Видаляємо нові колонки з таблиці tasks
    op.drop_column('tasks', 'scenario_id')
    op.drop_column('tasks', 'order_in_scenario')
    
    # Повертаємо старі колонки в таблицю tasks
    op.add_column('tasks', sa.Column('is_completed', sa.Boolean(), nullable=True, server_default='false'))
    
    # Видаляємо таблицю quest_scenarios
    op.drop_table('quest_scenarios') 