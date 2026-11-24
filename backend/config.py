from datetime import timedelta
from pathlib import Path


SYSTEM_PLAYER_ID = 1
SYSTEM_PLAYER_USERNAME = "володар лісу"
AVATAR_DIR = Path(__file__).resolve().parents[1] / "frontend" / "user_resourses" / "avatars"
RESOURCE_FILE = Path(__file__).resolve().parents[1] / "content" / "character_resources.json"
LEGACY_BALANCES = {"gold", "singing_resin", "basalt_bone"}
ENTERPRISE_SHIFT_DURATION = timedelta(hours=1)
