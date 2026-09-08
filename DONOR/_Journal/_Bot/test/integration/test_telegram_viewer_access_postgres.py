import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import load_environment
from app.core.access import AccessRole
from app.infrastructure.persistence.database import get_test_database_url
from app.infrastructure.persistence.models import TelegramViewerGrantORM
from app.infrastructure.persistence.telegram_access import TelegramAccessStore


def test_postgres_manual_viewer_grant_and_revoke():
    load_environment()
    if not os.getenv("TEST_DATABASE_URL", "").strip():
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    owner_telegram_id = 42
    viewer_telegram_id = 1_000_000_000 + (uuid4().int % 1_000_000_000_000)

    async def verify():
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        store = TelegramAccessStore(factory)
        try:
            assert await store.resolve_role(owner_telegram_id, owner_telegram_id) is AccessRole.OWNER
            assert await store.resolve_role(viewer_telegram_id, owner_telegram_id) is None

            assert await store.grant_viewer(viewer_telegram_id) is True
            assert await store.resolve_role(viewer_telegram_id, owner_telegram_id) is AccessRole.VIEWER
            assert await store.grant_viewer(viewer_telegram_id) is False

            assert await store.revoke_viewer(viewer_telegram_id) is True
            assert await store.resolve_role(viewer_telegram_id, owner_telegram_id) is None
            assert await store.revoke_viewer(viewer_telegram_id) is False
        finally:
            async with factory() as session:
                async with session.begin():
                    await session.execute(
                        delete(TelegramViewerGrantORM).where(
                            TelegramViewerGrantORM.telegram_user_id == viewer_telegram_id
                        )
                    )
            await engine.dispose()

    asyncio.run(verify())
