"""Alembic migration environment.

This file connects Alembic to the application's SQLAlchemy models so schema
changes can be generated and applied through migrations.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.models import Base

# Alembic Config object, loaded from alembic.ini.
config = context.config

# Configure Python logging from alembic.ini if logging config exists.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use DATABASE_URL from the environment when available.
# This keeps local runs, Docker, and CI aligned.
database_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/docclassifier",
)

# Alembic runs migrations synchronously, so we convert the async driver URL
# into a synchronous PostgreSQL URL for migration generation/execution.
sync_database_url = database_url.replace(
    "postgresql+asyncpg://",
    "postgresql://",
)

config.set_main_option("sqlalchemy.url", sync_database_url)

# Alembic compares this metadata against the database schema.
# This is why app.db.models.Base must include all ORM models.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating a DB engine.

    Offline mode emits SQL statements instead of connecting directly.
    """
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live database connection.

    This is the normal mode used by `alembic upgrade head` and autogenerate.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()