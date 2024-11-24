import os
from sqlalchemy import create_engine, MetaData, text

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'backend','database', 'users.db')}"
engine = create_engine(DATABASE_URL)
connection = engine.connect()
metadata = MetaData()


connection.execute(text('ALTER TABLE users ADD COLUMN pending_attribute_points INTEGER DEFAULT 0'))

print("Column 'avatar_url' added successfully.")

connection.close()
