from requests import Session

from backend import models
from backend.helpers import calc


class HelperMethods:

    def update_user_level(user: models.User, db: Session):
        """Перевіряє, чи досить досвіду для підвищення рівня, і підвищує рівень."""
        next_level_exp = calc.CalsculateExpForNextLvl.experience_needed_for_next_level(
            user.level
        )
        try:
            if user.experience >= next_level_exp:
                # Підвищуємо рівень
                user.level += 1
                user.experience -= (
                    next_level_exp  # Віднімаємо досвід для наступного рівня
                )
                db.commit()
        except TypeError as err:
            if next_level_exp is None:
                return
            raise TypeError("smth went wrong")


def get_available_units(level: int, db: Session):
    """Повертає доступні типи військ в залежності від рівня."""
    return (
        db.query(models.UnitType).filter(models.UnitType.level_required <= level).all()
    )


def add_units_to_user(user: models.User, unit_type_id: int, quantity: int, db: Session):
    """Додає одиниці війська користувачу."""
    unit_type = (
        db.query(models.UnitType).filter(models.UnitType.id == unit_type_id).first()
    )

    # Перевірка максимального ліміту
    if quantity < 0 or quantity > 10:
        raise ValueError("Кількість юнітів повинна бути між 0 та 10.")

    user_unit = (
        db.query(models.UserUnit)
        .filter(
            models.UserUnit.user_id == user.id,
            models.UserUnit.unit_type_id == unit_type_id,
        )
        .first()
    )

    if user_unit:
        user_unit.quantity = quantity  # Оновлюємо кількість
    else:
        user_unit = models.UserUnit(
            user_id=user.id, unit_type_id=unit_type_id, quantity=quantity
        )
        db.add(user_unit)

    db.commit()
