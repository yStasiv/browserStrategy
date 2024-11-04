from flask import Flask, request, jsonify, render_template, redirect, url_for, session
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
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Введіть логін та пароль'}), 400

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({'message': 'Користувач з таким ім’ям уже існує'}), 400
    finally:
        conn.close()

    return jsonify({'message': 'Реєстрація пройшла успішно'}), 201

# Авторизація користувача
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
       data = request.json
       username = data.get('username')
       password = data.get('password')

       conn = sqlite3.connect(db_path)
       cursor = conn.cursor()
       cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
       user = cursor.fetchone()
       conn.close()

       if user:
           # Зберігаємо ідентифікатор користувача в сесії
        #    session['user_id'] = user.id
           # Перенаправляємо на сторінку персонажа
           return redirect(url_for('character'))
       else:
           return jsonify({'message': 'Невірний логін або пароль'}), 401
       
    return render_template('index.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)  # Видаляємо user_id з сесії
    return redirect(url_for('login'))


@app.route('/character')
def character():
    # Перевіряємо, чи користувач залогінений
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    if not user:
        return redirect(url_for('login'))
    
    return render_template('character.html', user=user)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Створює таблиці, якщо їх ще немає
    app.run(debug=True)

