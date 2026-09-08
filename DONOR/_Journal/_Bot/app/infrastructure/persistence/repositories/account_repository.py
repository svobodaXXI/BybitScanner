"""SQLAlchemy async adapter for Account identity and internal owner scope."""

from sqlalchemy import exists, select

from app.application.ports.repositories import AccountRepository
from app.core.accounts.account_id import AccountId
from app.core.owners import OwnerId

from ..models.account import AccountORM
from ..models.owner import AccountOwnerORM
from ._common import require_session


class SqlAlchemyAccountRepository(AccountRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def exists(self, account_id: AccountId) -> bool:
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        return bool(await self._session.scalar(select(exists().where(AccountORM.id == account_id.value))))

    async def list_active(self) -> tuple[AccountId, ...]:
        result = await self._session.scalars(select(AccountORM).order_by(AccountORM.created_at.asc(), AccountORM.id.asc()))
        return tuple(AccountId(model.id) for model in result)

    async def list_for_owner(self, owner_id: OwnerId) -> tuple[AccountId, ...]:
        if not isinstance(owner_id, OwnerId):
            raise TypeError("owner_id must be OwnerId")
        result = await self._session.scalars(
            select(AccountORM)
            .join(AccountOwnerORM, AccountOwnerORM.account_id == AccountORM.id)
            .where(AccountOwnerORM.owner_id == owner_id.value)
            .order_by(AccountORM.created_at.asc(), AccountORM.id.asc())
        )
        return tuple(AccountId(model.id) for model in result)

    async def belongs_to_owner(self, account_id: AccountId, owner_id: OwnerId) -> bool:
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        if not isinstance(owner_id, OwnerId):
            raise TypeError("owner_id must be OwnerId")
        statement = select(
            exists().where(
                AccountOwnerORM.account_id == account_id.value,
                AccountOwnerORM.owner_id == owner_id.value,
            )
        )
        return bool(await self._session.scalar(statement))
