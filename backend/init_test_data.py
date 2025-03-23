from sqlalchemy.orm import Session
from . import models

def init_test_data(db: Session):
    """Ініціалізує тестові дані при запуску сервера"""
    
    # Перевіряємо чи існує сценарій з ID=1
    scenario = db.query(models.QuestScenario).filter(models.QuestScenario.id == 1).first()
    if not scenario:
        # Створюємо тестовий сценарій
        scenario = models.QuestScenario(
            id=1,
            title="Початкові завдання",
            description="Базові завдання для нових гравців",
            min_level=1,
            is_active=True
        )
        db.add(scenario)
        db.flush()

        # Створюємо тестові завдання
        tasks = [
            models.Task(
                id=1,
                scenario_id=scenario.id,
                title="Перше завдання",
                description="Ознайомтесь з гільдією авантюристів",
                level_required=1,
                order_in_scenario=1,
                reward_exp=50
            ),
            models.Task(
                id=2,
                scenario_id=scenario.id,
                title="Збір ресурсів",
                description="Зберіть 10 одиниць дерева",
                level_required=1,
                order_in_scenario=2,
                reward_gold=10,
                reward_exp=30
            ),
            models.Task(
                id=3,
                scenario_id=scenario.id,
                title="Робота на лісопилці",
                description="Попрацюйте на лісопилці протягом 5 хвилин",
                level_required=1,
                order_in_scenario=3,
                reward_gold=20,
                reward_exp=40
            )
        ]
        
        for task in tasks:
            db.add(task)

        # Створюємо тестовий сценарій вищого рівня
        advanced_scenario = models.QuestScenario(
            id=2,
            title="Завдання досвідченого авантюриста",
            description="Завдання для досвідчених гравців",
            min_level=2,
            is_active=True
        )
        db.add(advanced_scenario)
        db.flush()

        # Додаємо завдання вищого рівня
        advanced_tasks = [
            models.Task(
                id=4,
                scenario_id=advanced_scenario.id,
                title="Збір каменю",
                description="Зберіть 20 одиниць каменю",
                level_required=2,
                order_in_scenario=1,
                reward_gold=30,
                reward_exp=60
            ),
            models.Task(
                id=5,
                scenario_id=advanced_scenario.id,
                title="Робота в шахті",
                description="Попрацюйте в шахті протягом 10 хвилин",
                level_required=2,
                order_in_scenario=2,
                reward_gold=40,
                reward_stone=5,
                reward_exp=80
            )
        ]
        
        for task in advanced_tasks:
            db.add(task)

        # # Додаємо початкове досягнення
        # achievement = db.query(models.Achievement).filter(models.Achievement.id == 1).first()
        # if not achievement:
        #     achievement = models.Achievement(
        #         id=1,
        #         title="Початок шляху",
        #         description="Виконайте своє перше завдання в гільдії авантюристів",
        #         icon_url="../static/images/achievements/first-quest.png"  # Додайте відповідну іконку
        #     )
        #     db.add(achievement)
        #     db.commit()

        db.commit()
        print("Тестові дані успішно створено")

def init_test_admin(db: Session):
    """Створює тестового адміністратора, якщо його ще немає"""
    admin = db.query(models.User).filter(models.User.id == 1).first()
    if not admin:
        from backend.routers.auth import hash_password
        admin = models.User(
            id=1,
            username="1",
            password=hash_password("1"),
            fraction="Admin",
            gold=1000000,
            wood=1000000,
            stone=1000000,
            level=100,
        )
        db.add(admin)
        db.commit()
        print("Створено тестового адміністратора (login: 1, password: 1)") 