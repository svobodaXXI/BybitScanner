"""Async Alembic environment using the application's DATABASE_URL boundary."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection

from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.database import create_async_engine, get_database_url
from app.infrastructure.persistence import models as _models  # noqa: F401 - register all tables


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configured_url() -> str:
    try:
        return get_database_url()
    except ValueError as error:
        raise RuntimeError("DATABASE_URL must be set before running Alembic") from error


def run_migrations_offline() -> None:
    context.configure(
        url=_configured_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        _configured_url(),
        engine_options={"poolclass": pool.NullPool},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
