"""Infrastructure-only async PostgreSQL engine/session factories."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
from sqlalchemy.engine import make_url

from app.config import load_environment


def get_database_url(database_url: str | None = None) -> str:
    """Resolve an explicit URL or DATABASE_URL without loading env in Domain code."""
    load_environment()
    resolved = database_url or os.getenv("DATABASE_URL")
    if resolved is None or not resolved.strip():
        raise ValueError("DATABASE_URL is required")
    return resolved.strip()


def get_test_database_url(database_url: str | None = None) -> str:
    """Resolve TEST_DATABASE_URL only; never fall back to the runtime database."""
    load_environment()
    resolved = database_url or os.getenv("TEST_DATABASE_URL")
    if resolved is None or not resolved.strip():
        raise ValueError("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return resolved.strip()


def mask_database_url(database_url: str) -> str:
    """Return a database URL safe for logs, with credentials replaced."""
    if not isinstance(database_url, str) or not database_url.strip():
        return "<not configured>"
    try:
        parsed = make_url(database_url.strip())
        if parsed.password is None:
            return parsed.render_as_string(hide_password=True)
        return parsed.set(password="***").render_as_string(hide_password=False)
    except Exception:
        return "<invalid database url>"


def create_async_engine(
    database_url: str | None = None,
    *,
    engine_options: Mapping[str, Any] | None = None,
) -> AsyncEngine:
    """Create an async engine; construction does not establish a DB connection."""
    return _create_async_engine(get_database_url(database_url), **dict(engine_options or {}))


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async sessionmaker with stable object lifetimes for application use."""
    return async_sessionmaker(engine, expire_on_commit=False)
