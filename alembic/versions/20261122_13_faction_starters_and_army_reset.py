"""Grant faction starter buildings and reset the saved army roster."""

import sqlalchemy as sa
from alembic import context, op

revision = "20261122_13"
down_revision = "20261122_12"
branch_labels = None
depends_on = None

STARTERS = {
    "elves": ("elves_recruitment_tier_1", "elves_recruitment_tier_2"),
    "undergroundelves": ("underground_elves_recruitment_tier_1", "underground_elves_recruitment_tier_2"),
}


def upgrade():
    keep_player = context.get_x_argument(as_dictionary=True).get("keep_faction_army")
    if keep_player is not None:
        keep_player = int(keep_player)
    op.execute("UPDATE users SET fraction = 'undergroundElves' WHERE lower(fraction) IN ('darkelfe', 'underground_elves')")
    op.execute("UPDATE unit_types SET fraction = 'undergroundElves' WHERE lower(fraction) IN ('darkelfe', 'underground_elves')")
    grant = sa.text("""
        INSERT INTO castle_buildings (player_id, building_id)
        SELECT users.id, :building FROM users
        WHERE (CASE WHEN lower(users.fraction) = 'elfe' THEN 'elves' ELSE lower(users.fraction) END) = :faction
          AND NOT EXISTS (
            SELECT 1 FROM castle_buildings
            WHERE player_id = users.id AND building_id = :building
          )
    """)
    for faction, buildings in STARTERS.items():
        for building in buildings:
            op.execute(grant.bindparams(faction=faction, building=building))

    # Active and finished battles keep their independent snapshots.
    if keep_player is None:
        op.execute("DELETE FROM army_slots")
    else:
        op.execute(sa.text("""
            DELETE FROM army_slots
            WHERE NOT EXISTS (
                SELECT 1 FROM users
                WHERE users.id = army_slots.user_id AND users.id = :keep_player
                  AND (
                      (lower(users.fraction) IN ('elfe', 'elves') AND substr(unit_key, 1, 6) = 'elves_')
                      OR (lower(users.fraction) = 'undergroundelves' AND substr(unit_key, 1, 18) = 'underground_elves_')
                  )
            )
        """).bindparams(keep_player=keep_player))


def downgrade():
    # Reset rosters can only be recovered from a database backup.
    op.execute("UPDATE users SET fraction = 'darkElfe' WHERE lower(fraction) = 'undergroundelves'")
    op.execute("UPDATE unit_types SET fraction = 'darkElfe' WHERE lower(fraction) = 'undergroundelves'")
