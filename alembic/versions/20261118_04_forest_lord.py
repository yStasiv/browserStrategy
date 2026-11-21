"""Make the technical player a playable character."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_04"
down_revision = "20261118_03"
branch_labels = None
depends_on = None

PLAYABLE_NAME = "володар лісу"
TECHNICAL_NAME = "__system__"
STATS = (
    "stamina", "energy", "agility", "mind", "melee_attack", "ranged_attack",
    "magic_power", "physical_defense", "magic_resistance", "bonus_melee_damage",
    "bonus_ranged_damage", "bonus_magic_damage", "bonus_melee_defense",
    "bonus_ranged_defense", "bonus_magic_defense",
)


def rename_system_player(new_name, **changes):
    connection = op.get_bind()
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    target = sa.and_(users.c.id == 1, users.c.is_system.is_(True))
    if connection.scalar(sa.select(users.c.id).where(target)) is None:
        raise RuntimeError("The migrated technical account at ID 1 is required.")
    if connection.scalar(sa.select(users.c.id).where(
        users.c.username == new_name, users.c.id != 1
    )) is not None:
        raise RuntimeError(f"The system player name {new_name!r} is already in use.")
    connection.execute(users.update().where(target).values(username=new_name, **changes))


def upgrade():
    defaults = {stat: sa.func.coalesce(sa.column(stat), 0) for stat in STATS}
    rename_system_player(
        PLAYABLE_NAME,
        is_active=True,
        session_id=None,
        fraction=sa.case((sa.column("fraction") == "System", "elfe"), else_=sa.column("fraction")),
        pending_attribute_points=sa.func.coalesce(sa.column("pending_attribute_points"), 1),
        **defaults,
    )


def downgrade():
    rename_system_player(TECHNICAL_NAME, is_active=False, session_id=None)
