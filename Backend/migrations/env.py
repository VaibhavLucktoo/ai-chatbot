from logging.config import fileConfig
from typing import Any

from alembic import context
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import URL, create_engine, pool

from app.core.config import get_settings
from app.storage.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.postgres_user,
    password=settings.postgres_password.get_secret_value(),
    host=settings.db_host,
    port=settings.db_port,
    database=settings.postgres_db,
)


def render_item(
    item_type: str,
    obj: Any,
    autogen_context: Any,
) -> str | bool:
    """Make generated vector-column imports explicit."""
    if item_type == "type" and isinstance(obj, VECTOR):
        autogen_context.imports.add(
            "from pgvector.sqlalchemy import VECTOR"
        )
        return f"VECTOR({obj.dim})"

    return False


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        database_url,
        poolclass=pool.NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": "-c lock_timeout=5000",
        },
    )

    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                compare_type=True,
                render_item=render_item,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()