from alembic import op
import sqlalchemy as sa
from datetime import datetime

def upgrade():
    # Додаємо нові поля до таблиці users
    op.add_column('users', sa.Column('workplace', sa.String(), nullable=True))
    op.add_column('users', sa.Column('last_salary_time', sa.DateTime(), nullable=True))
    
    # Створюємо таблицю sawmill
    op.create_table(
        'sawmill',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wood_stored', sa.Integer(), nullable=False, default=0),
        sa.Column('last_production_time', sa.DateTime(), nullable=True),
        sa.Column('workers_count', sa.Integer(), nullable=False, default=0),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Створюємо початковий запис для лісопилки
    op.execute(
        "INSERT INTO sawmill (id, wood_stored, workers_count) VALUES (1, 0, 0)"
    )

def downgrade():
    op.drop_column('users', 'workplace')
    op.drop_column('users', 'last_salary_time')
    op.drop_table('sawmill') 