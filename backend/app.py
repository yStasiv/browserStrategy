from flask import Flask, request, jsonify, render_template, redirect, url_for,flash, session
from models import db, User


import sqlite3
import os

app = Flask(
    __name__,
    template_folder=os.path.join("..", "frontend", "templates"),
    static_folder=os.path.join("..", "frontend", "static")
)
db_path = os.path.join(os.path.dirname(__file__), "database", "users.db")
app.secret_key = 'your_secret_key'  # Необхідно для роботи сесій


# Конфігурація для бази даних
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////workspaces/browserStrategy/backend/database/users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ініціалізуємо SQLAlchemy з об'єктом app
db.init_app(app)

# Реєстрація користувача
@app.route('/register', methods=['POST'])
def register():
    username = request.form['regUsername']
    password = request.form['regPassword']
    if not username or not password:  # TODO не використовуємо цю перевірку
        return jsonify({'message': 'Введіть логін та пароль'}), 400

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash({'message': 'Користувач з таким ім’ям уже існує'}), 400  #TODO add notification aboust success on invalid creds
        return render_template('index.html')
    
    new_user = User(username=username, password=password)
    db.session.add(new_user)
    db.session.commit()
    flash('Реєстрація пройшла успішно', 201)
    return render_template('index.html')

# Авторизація користувача
@app.route('/login', methods=['GET', 'POST'])
def login():
   if request.method == 'POST':
        username = request.form['loginUsername']
        password = request.form['loginPassword']
        # Перевірка існування користувача в базі даних через SQLAlchemy
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            # Зберігаємо user_id у сесії після успішної авторизації
            session['user_id'] = user.id
            return redirect(url_for('character'))
        
        # Повертаємо помилку, якщо логін або пароль неправильні
        flash({'message': 'Невірний логін або пароль'}), 401
        return render_template('index.html')

   return render_template('index.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Видаляємо user_id з сесії
    return redirect(url_for('login'))


@app.route('/character')
def character():
    user_id = session['user_id']
    if not user_id:
        return redirect(url_for('login'))
    user = User.query.get(user_id)  # Використовуємо SQLAlchemy для отримання користувача за ID
    if user:
        return render_template('character.html', user=user)
    else:
        return redirect(url_for('login'))  # Якщо користувача немає, переходимо на сторінку входу

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Створює таблиці, якщо їх ще немає
    app.run(debug=True)

