import asyncio
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import load_environment
from app.core.accounts.account_id import AccountId
from app.core.owners import OwnerId
from app.infrastructure.persistence.database import get_test_database_url
from app.infrastructure.persistence.models import AccountORM, AccountOwnerORM, OwnerORM
from app.infrastructure.persistence.repositories import SqlAlchemyAccountRepository


def test_postgres_account_repository_isolates_accounts_by_owner():
    load_environment()
    if not os.getenv("TEST_DATABASE_URL", "").strip():
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL integration tests skipped")

    owner_a = OwnerId.generate()
    owner_b = OwnerId.generate()
    account_a = AccountId.generate()
    account_b = AccountId.generate()
    created_at = datetime.now(timezone.utc)

    async def verify():
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    session.add_all(
                        [
                            OwnerORM(id=owner_a.value, created_at=created_at),
                            OwnerORM(id=owner_b.value, created_at=created_at),
                            AccountORM(id=account_a.value, created_at=created_at),
                            AccountORM(id=account_b.value, created_at=created_at),
                        ]
                    )
                    await session.flush()
                    session.add_all(
                        [
                            AccountOwnerORM(account_id=account_a.value, owner_id=owner_a.value, created_at=created_at),
                            AccountOwnerORM(account_id=account_b.value, owner_id=owner_b.value, created_at=created_at),
                        ]
                    )

            async with factory() as session:
                repository = SqlAlchemyAccountRepository(session)
                assert await repository.list_for_owner(owner_a) == (account_a,)
                assert await repository.list_for_owner(owner_b) == (account_b,)
                assert await repository.belongs_to_owner(account_a, owner_a) is True
                assert await repository.belongs_to_owner(account_a, owner_b) is False
                assert await repository.belongs_to_owner(account_b, owner_b) is True
                assert await repository.belongs_to_owner(account_b, owner_a) is False
        finally:
            async with factory() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(delete(AccountOwnerORM).where(AccountOwnerORM.account_id.in_([account_a.value, account_b.value])))
                    await cleanup.execute(delete(AccountORM).where(AccountORM.id.in_([account_a.value, account_b.value])))
                    await cleanup.execute(delete(OwnerORM).where(OwnerORM.id.in_([owner_a.value, owner_b.value])))
            await engine.dispose()

    asyncio.run(verify())
