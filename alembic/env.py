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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
