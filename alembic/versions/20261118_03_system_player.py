"""Reserve the system player and record enterprise ownership and reward issuance."""

import sqlalchemy as sa
from alembic import op

revision = "20261118_03"
down_revision = "20261118_02"
branch_labels = None
depends_on = None

SYSTEM_ID = 1
SYSTEM_USERNAME = "__system__"
USER_REFERENCES = {
    ("army_slots", "user_id"), ("battle_histories", "user_id"),
    ("battle_participants", "user_id"), ("battle_state", "user_id"),
    ("equipped_items", "user_id"), ("guild_processed_events", "player_id"),
    ("guild_progress", "player_id"), ("items", "owner_id"),
    ("player_ratings", "user_id"), ("user_achievements", "user_id"),
    ("user_tasks", "user_id"), ("user_units", "user_id"),
}
GUILD_REFERENCES = {
    ("guild_daily_replacements", "player_id"), ("guild_quest_instances", "player_id"),
    ("guild_quest_slots", "player_id"),
}


def verify_references(connection, existing_empty_ledger):
    inspector = sa.inspect(connection)
    expected = {
        ("users", ("id",)): USER_REFERENCES,
        ("guild_progress", ("player_id",)): GUILD_REFERENCES,
        ("guild_quest_instances", ("player_id", "id")): {("guild_quest_slots", "player_id")},
    }
    for table in inspector.get_table_names():
        if existing_empty_ledger and table == "reward_transactions":
            continue
        for fk in inspector.get_foreign_keys(table):
            target = (fk["referred_table"], tuple(fk["referred_columns"]))
            if target in expected and (table, fk["constrained_columns"][0]) not in expected[target]:
                raise RuntimeError(f"Review unexpected account reference in {table}: {fk}")


def move_admin(connection, users, admin):
    new_id = connection.scalar(sa.select(sa.func.max(users.c.id))) + 1
    # Free unique fields before inserting the preserved record at its new ID.
    connection.execute(users.update().where(users.c.id == SYSTEM_ID).values(
        username=None, email=None, session_id=None
    ))
    connection.execute(users.insert().values(
        dict(admin, id=new_id, session_id=None, is_admin=True, is_system=False)
    ))

    metadata = sa.MetaData()
    def table(name):
        return sa.Table(name, metadata, autoload_with=connection)
    progress = table("guild_progress")
    old_progress = connection.execute(
        sa.select(progress).where(progress.c.player_id == SYSTEM_ID)
    ).mappings().one_or_none()
    if old_progress is not None:
        connection.execute(progress.insert().values(dict(old_progress, player_id=new_id)))
        slots = table("guild_quest_slots")
        slot_filter = slots.c.player_id == SYSTEM_ID
        old_slots = connection.execute(sa.select(slots).where(slot_filter)).mappings().all()
        connection.execute(slots.delete().where(slot_filter))
        for name, column in sorted(GUILD_REFERENCES - {("guild_quest_slots", "player_id")}):
            child = table(name)
            connection.execute(child.update().where(child.c[column] == SYSTEM_ID).values({column: new_id}))
        if old_slots:
            connection.execute(slots.insert(), [dict(slot, player_id=new_id) for slot in old_slots])
        connection.execute(progress.delete().where(progress.c.player_id == SYSTEM_ID))

    for name, column in sorted(USER_REFERENCES - {("guild_progress", "player_id")}):
        child = table(name)
        connection.execute(child.update().where(child.c[column] == SYSTEM_ID).values({column: new_id}))
    connection.execute(users.delete().where(users.c.id == SYSTEM_ID))


def upgrade():
    connection = op.get_bind()
    if op.get_context().as_sql:
        raise RuntimeError("The system player migration requires a live database for account checks.")
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    admin = connection.execute(sa.select(users).where(users.c.id == SYSTEM_ID)).mappings().one_or_none()
    if admin is not None and (admin["username"], admin["fraction"]) != ("1", "Admin"):
        raise RuntimeError("Player ID 1 is occupied by an unrecognized account. Review before migrating.")
    if connection.scalar(sa.select(users.c.id).where(users.c.username == SYSTEM_USERNAME)) is not None:
        raise RuntimeError("The reserved system username is already in use.")
    existing_empty_ledger = sa.inspect(connection).has_table("reward_transactions")
    if existing_empty_ledger:
        ledger = sa.Table("reward_transactions", sa.MetaData(), autoload_with=connection)
        if connection.scalar(sa.select(sa.func.count()).select_from(ledger)):
            raise RuntimeError("Unexpected reward history requires review before account migration.")
    verify_references(connection, existing_empty_ledger)

    op.add_column("users", sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    if admin is not None:
        move_admin(connection, users, admin)
    connection.execute(users.insert().values(
        id=SYSTEM_ID, username=SYSTEM_USERNAME, fraction="System", is_active=False,
        is_system=True, is_admin=False, gold=0, wood=0, stone=0, level=1,
        experience=0, map_sector="Castle", map_x=0, map_y=0,
    ))
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("""
            SELECT setval(pg_get_serial_sequence('users', 'id'),
                GREATEST((SELECT MAX(id) FROM users), nextval(pg_get_serial_sequence('users', 'id'))))
        """))

    with op.batch_alter_table("enterprises") as batch:
        batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=False, server_default=sa.text("1")))
        batch.create_foreign_key("fk_enterprises_owner_id_users", "users", ["owner_id"], ["id"])
        batch.create_index("ix_enterprises_owner_id", ["owner_id"])

    if existing_empty_ledger:
        # A previous app startup may have created this empty table from model metadata.
        op.drop_table("reward_transactions")

    op.create_table(
        "reward_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issuer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("gold", sa.Integer(), nullable=False),
        sa.Column("wood", sa.Integer(), nullable=False),
        sa.Column("stone", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source", "source_key", "recipient_id", name="uq_reward_transaction_source"),
    )


def downgrade():
    raise RuntimeError("Restore a pre-migration database backup to reverse account reassignment.")
