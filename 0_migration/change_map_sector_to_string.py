from alembic import op
import sqlalchemy as sa

def upgrade():
    # Спочатку конвертуємо існуючі значення в рядки
    op.execute("UPDATE users SET map_sector = CAST(map_sector AS VARCHAR)")
    
    # Змінюємо тип колонки
    op.alter_column('users', 'map_sector',
                    existing_type=sa.INTEGER(),
                    type_=sa.String(),
                    postgresql_using='map_sector::varchar',
                    existing_nullable=True)

def downgrade():
    op.alter_column('users', 'map_sector',
                    existing_type=sa.String(),
                    type_=sa.INTEGER(),
                    postgresql_using='map_sector::integer',
                    existing_nullable=True) 