import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.db import Base, make_engine
from app.settings import get_settings

config = context.config

if config.config_file_name is not None:
    # Keep the loggers that already exist (the app's, uvicorn's): by default fileConfig silences
    # them, which matters now that the app runs the migrations itself at startup.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The URL comes from Settings. alembic.ini only holds a placeholder, so a URL set beforehand
# (a test, for example) is kept and the placeholder is replaced.
if config.get_main_option("sqlalchemy.url", "").startswith("driver://"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Autogenerate compares the database against these models.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit the SQL as a script, without connecting to the database."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER columns, so changes are done by rebuilding the table.
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # make_engine creates the database folder and sets the SQLite PRAGMAs, like the app does.
    connectable = make_engine(config.get_main_option("sqlalchemy.url", ""))

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
