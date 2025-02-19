import os
from sqlalchemy import create_engine, MetaData, text, inspect

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'backend','database', 'users.db')}"
engine = create_engine(DATABASE_URL)
connection = engine.connect()
metadata = MetaData()

# Отримуємо інспектор для перевірки структури бази даних
inspector = inspect(engine)

# Перевіряємо і додаємо колонки до таблиці users, якщо їх ще немає
existing_columns = [col['name'] for col in inspector.get_columns('users')]

if 'workplace' not in existing_columns:
    connection.execute(text('ALTER TABLE users ADD COLUMN workplace STRING DEFAULT null'))

if 'last_salary_time' not in existing_columns:
    connection.execute(text('ALTER TABLE users ADD COLUMN last_salary_time DATETIME DEFAULT null'))

# Перевіряємо чи існує таблиця enterprises
if not inspector.has_table('enterprises'):
    # Створюємо таблицю enterprises
    connection.execute(text('''
        CREATE TABLE enterprises (
            id INTEGER PRIMARY KEY,
            name STRING NOT NULL,
            resource_stored INTEGER NOT NULL DEFAULT 0,
            last_production_time DATETIME DEFAULT null,
            workers_count INTEGER NOT NULL DEFAULT 0,
            max_workers INTEGER NOT NULL DEFAULT 10,
            max_storage INTEGER NOT NULL DEFAULT 666,
            resource_type STRING NOT NULL
        )
    '''))
    
    # Додаємо початковий запис для лісопилки
    connection.execute(text('''
        INSERT INTO enterprises (id, name, resource_stored, workers_count, max_workers, max_storage, resource_type)
        VALUES (1, 'sawmill', 0, 0, 10, 666, 'wood')
    '''))

# Додаємо нові поля
connection.execute(text('ALTER TABLE users ADD COLUMN last_quit_time DATETIME DEFAULT null'))
connection.execute(text('ALTER TABLE enterprises ADD COLUMN salary INTEGER DEFAULT 3'))
connection.execute(text('ALTER TABLE enterprises ADD COLUMN item_price INTEGER DEFAULT 11'))

# Додаємо лісопилки, якщо їх ще немає
connection.execute(text('''
    INSERT OR IGNORE INTO enterprises (id, name, resource_stored, workers_count, max_workers, max_storage, resource_type, salary, item_price)
    VALUES 
    (1, 'sawmill', 0, 0, 10, 666, 'wood', 3, 11),
    (2, 'sawmill', 0, 0, 10, 666, 'wood', 7, 11)
'''))

print("Migration completed successfully!")

def upgrade():
    # Додаємо нові поля до таблиці users
    connection.execute(text('ALTER TABLE users ADD COLUMN workplace STRING DEFAULT null'))
    connection.execute(text('ALTER TABLE users ADD COLUMN last_salary_time DATETIME DEFAULT null'))
    
    # Створюємо таблицю enterprises
    connection.execute(text('''
        CREATE TABLE IF NOT EXISTS enterprises (
            id INTEGER PRIMARY KEY,
            name STRING NOT NULL,
            resource_stored INTEGER NOT NULL DEFAULT 0,
            last_production_time DATETIME DEFAULT null,
            workers_count INTEGER NOT NULL DEFAULT 0,
            max_workers INTEGER NOT NULL DEFAULT 10,
            max_storage INTEGER NOT NULL DEFAULT 666,
            resource_type STRING NOT NULL
        )
    '''))
    
    # Створюємо початковий запис для лісопилки
    connection.execute(text('''
        INSERT INTO enterprises (id, name, resource_stored, workers_count, max_workers, max_storage, resource_type)
        VALUES (1, 'sawmill', 0, 0, 10, 666, 'wood')
    '''))

def downgrade():
    connection.execute(text('ALTER TABLE users DROP COLUMN workplace'))
    connection.execute(text('ALTER TABLE users DROP COLUMN last_salary_time'))
    connection.execute(text('DROP TABLE enterprises')) 