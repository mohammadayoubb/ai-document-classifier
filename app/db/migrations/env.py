"""Alembic environment — configures database migrations for this project.

This file teaches Alembic how to build the same Vault-aware database URL used
by the application and how to run migrations through SQLAlchemy's async engine.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.db.models import Base
from app.infra.vault import VaultClient

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return the DB URL using the same secret-aware settings path as the app.

    Returns:
        SQLAlchemy database URL for Alembic.

    Raises:
        RuntimeError: If Vault is required but unreachable.
    """
    settings = get_settings()
    if not settings.database_url and not settings.postgres_password:
        # VAULT CALL: migrations resolve the database password the same way the app does.
        vault_client = VaultClient(settings.vault_addr, settings.vault_token)
        if not vault_client.is_reachable():
            raise RuntimeError("Vault is unreachable or the configured token is invalid.")
        return settings.build_database_url_from_vault(vault_client)
    return settings.build_database_url()


def run_migrations_offline() -> None:
    """Run migrations without opening a DB connection.

    Offline mode emits SQL from metadata instead of connecting to the database.
    """
    # ALEMBIC CONFIG: provide URL and metadata for offline SQL generation.
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        # ALEMBIC CALL: execute pending migration scripts in offline mode.
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure Alembic with an existing connection and run migrations.

    Args:
        connection: Synchronous SQLAlchemy connection supplied by async bridge.
    """
    # ALEMBIC CONFIG: bind migration context to the live connection.
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        # ALEMBIC CALL: run migration scripts inside a transaction.
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync connection.

    Alembic itself is synchronous, so SQLAlchemy bridges the async connection
    into do_run_migrations().
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    # DB ENGINE: create a one-use async engine for the migration process.
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # ALEMBIC BRIDGE: run synchronous migration code on the async connection.
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations with a live async DB connection."""
    # ASYNC ENTRYPOINT: Alembic calls this from synchronous module scope.
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
