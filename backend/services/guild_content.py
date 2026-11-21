import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

QUESTS_FILE = Path(__file__).resolve().parents[2] / "content" / "guild_quests.json"


class QuestTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    category: Literal["collection", "delivery", "enemy_defeat", "hunting", "special"]
    resource: Literal["singing_resin", "basalt_bone"]
    difficulty: str = Field(min_length=1, max_length=32)
    min_level: int = Field(ge=1)
    required: int = Field(ge=1)
    gold: int = Field(ge=0)
    wood: int = Field(ge=0, validation_alias="singing_resin")
    stone: int = Field(ge=0, validation_alias="basalt_bone")
    xp: int = Field(ge=0)
    enabled: bool


TEMPLATES = TypeAdapter(list[QuestTemplate])


def load_templates():
    templates = TEMPLATES.validate_python(json.loads(QUESTS_FILE.read_text(encoding="utf-8")))
    if len({template.key for template in templates}) != len(templates):
        raise ValueError("Quest template keys must be unique")
    if sum(t.enabled and t.category == "collection" and t.min_level == 1 for t in templates) < 2:
        raise ValueError("At least two enabled collection templates must be available at level 1")
    return templates
