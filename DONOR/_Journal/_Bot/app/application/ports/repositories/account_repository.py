"""Repository port for trading-account identity and internal owner scope."""

from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.core.owners import OwnerId


@runtime_checkable
class AccountRepository(Protocol):
    """Account existence plus server-authoritative ownership queries."""

    async def exists(self, account_id: AccountId) -> bool:
        ...

    async def list_active(self) -> tuple[AccountId, ...]:
        """Return all active accounts for legacy/internal administration flows."""
        ...

    async def list_for_owner(self, owner_id: OwnerId) -> tuple[AccountId, ...]:
        """Return only trading accounts assigned to the internal owner."""
        ...

    async def belongs_to_owner(self, account_id: AccountId, owner_id: OwnerId) -> bool:
        """Verify account membership without trusting a client-supplied account id."""
        ...
