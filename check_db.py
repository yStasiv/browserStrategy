import os

from sqlalchemy import MetaData, Table, create_engine, text
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'backend','database', 'users.db')}"
engine = create_engine(DATABASE_URL)

# Створюємо сесію
Session = sessionmaker(bind=engine)
session = Session()

# Отримуємо метадані
metadata = MetaData()
metadata.reflect(bind=engine)

print("\nТаблиці в базі даних:")
for table_name in metadata.tables:
    print(f"- {table_name}")

print("\nСтруктура таблиці enterprises:")
enterprises_table = Table("enterprises", metadata, extend_existing=True)
for column in enterprises_table.columns:
    print(f"- {column.name}: {column.type}")

print("\nПідприємства в базі:")
with engine.connect() as connection:
    result = connection.execute(text("SELECT * FROM enterprises"))
    enterprises = result.fetchall()
    for enterprise in enterprises:
        print(enterprise)

print("\nПеревірка через ORM:")
from backend.models import Enterprise

enterprises_orm = session.query(Enterprise).all()
print(f"Кількість підприємств через ORM: {len(enterprises_orm)}")
for enterprise in enterprises_orm:
    print(f"ID: {enterprise.id}, Name: {enterprise.name}, Salary: {enterprise.salary}")
