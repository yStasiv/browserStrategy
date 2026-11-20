from alembic import context

from backend import guild_models, models
from backend.db_base import Base, engine
from backend.engine import battle_models

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=engine.url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        if connection.dialect.name == "sqlite":
            # Batch migrations rebuild referenced tables. Check integrity before committing.
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                    context.configure(connection=connection, target_metadata=target_metadata)
                    context.run_migrations()
                    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchmany(5)
                    if violations:
                        raise RuntimeError(f"SQLite foreign-key violations after migration: {violations}")
            finally:
                connection.exec_driver_sql(f"PRAGMA foreign_keys={int(foreign_keys)}")
        else:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
