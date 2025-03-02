import os
from sqlalchemy import create_engine, MetaData, text

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'backend','database', 'users.db')}"
engine = create_engine(DATABASE_URL)
connection = engine.connect()
metadata = MetaData()


connection.execute(text('ALTER TABLE tasks ADD COLUMN is_initial BOOLEAN DEFAULT FALSE'))  # add column
# connection.execute(text('ALTER TABLE enterprises ADD COLUMN production_type STRING DEFAULT "mine"'))  # add column
# connection.execute(text('ALTER TABLE users DROP COLUMN map_н'))  # drop column
# connection.execute(text("UPDATE users SET map_x = :value"), {"value": 50})  # update column



# Додати нове підприємство
# connection.execute(text('''
#     INSERT INTO enterprises (id, name, resource_stored, workers_count, max_workers, max_storage, resource_type, salary)
#     VALUES (2, 'sawmill', 0, 0, 10, 666, 'wood', 7)
# '''))
connection.commit()  # Не забудь зберегти зміни після оновлення даних в стовбці

print("Column 'avatar_url' added successfully.")

connection.close()
