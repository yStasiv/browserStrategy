"""File containe calcs for game mechanics"""
class CalsculateExpForNextLvl():

    def experience_needed_for_next_level(level: int) -> int:
        """Обчислює необхідний досвід для досягнення наступного рівня."""
        if level >= 8:
            return None  # Гравець досяг максимального рівня
        base_experience = 1000
        return int(base_experience * (1.3 ** (level - 1)))