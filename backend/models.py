# backend/models.py

from flask_sqlalchemy import SQLAlchemy

# Створюємо об'єкт SQLAlchemy, який потім будемо імпортувати
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    level = db.Column(db.Integer, default=1)
    gold = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<User {self.username}>'
