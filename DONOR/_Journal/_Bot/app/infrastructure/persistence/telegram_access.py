"""Persistence-backed Telegram access grants for the current single-owner journal."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, exists, select

from app.core.access import AccessRole
from app.core.accounts.account_id import AccountId
from app.core.owners import LEGACY_SINGLE_OWNER_ID, OwnerId
from app.core.trades.trade_id import TradeId

from .database import create_session_factory
from .models.owner import AccountOwnerORM, TelegramViewerGrantORM
from .models.trade import TradeORM


class TelegramAccessStore:
    """Resolve the configured owner and manually approved read-only viewers."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @classmethod
    def from_engine(cls, engine) -> "TelegramAccessStore":
        return cls(create_session_factory(engine))

    @staticmethod
    def _telegram_user_id(value: int) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError("telegram_user_id must be a positive integer")
        return value

    async def resolve_role(self, telegram_user_id: int, owner_telegram_user_id: int | None) -> AccessRole | None:
        telegram_user_id = self._telegram_user_id(telegram_user_id)
        if owner_telegram_user_id is not None and telegram_user_id == owner_telegram_user_id:
            return AccessRole.OWNER
        async with self._session_factory() as session:
            granted = await session.scalar(
                select(
                    exists().where(
                        TelegramViewerGrantORM.telegram_user_id == telegram_user_id,
                        TelegramViewerGrantORM.owner_id == LEGACY_SINGLE_OWNER_ID.value,
                    )
                )
            )
        return AccessRole.VIEWER if granted else None

    async def grant_viewer(
        self,
        telegram_user_id: int,
        *,
        owner_id: OwnerId = LEGACY_SINGLE_OWNER_ID,
    ) -> bool:
        telegram_user_id = self._telegram_user_id(telegram_user_id)
        if not isinstance(owner_id, OwnerId):
            raise TypeError("owner_id must be OwnerId")
        async with self._session_factory() as session:
            async with session.begin():
                current = await session.get(TelegramViewerGrantORM, telegram_user_id)
                if current is not None:
                    if current.owner_id != owner_id.value:
                        current.owner_id = owner_id.value
                    return False
                session.add(
                    TelegramViewerGrantORM(
                        telegram_user_id=telegram_user_id,
                        owner_id=owner_id.value,
                        created_at=datetime.now(timezone.utc),
                    )
                )
        return True

    async def revoke_viewer(
        self,
        telegram_user_id: int,
        *,
        owner_id: OwnerId = LEGACY_SINGLE_OWNER_ID,
    ) -> bool:
        telegram_user_id = self._telegram_user_id(telegram_user_id)
        if not isinstance(owner_id, OwnerId):
            raise TypeError("owner_id must be OwnerId")
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    delete(TelegramViewerGrantORM).where(
                        TelegramViewerGrantORM.telegram_user_id == telegram_user_id,
                        TelegramViewerGrantORM.owner_id == owner_id.value,
                    )
                )
                return bool(result.rowcount)

    async def account_belongs_to_owner(
        self,
        account_id: AccountId | str,
        *,
        owner_id: OwnerId = LEGACY_SINGLE_OWNER_ID,
    ) -> bool:
        account = account_id if isinstance(account_id, AccountId) else AccountId(account_id)
        async with self._session_factory() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            AccountOwnerORM.account_id == account.value,
                            AccountOwnerORM.owner_id == owner_id.value,
                        )
                    )
                )
            )

    async def trade_belongs_to_owner(
        self,
        trade_id: TradeId | str,
        *,
        owner_id: OwnerId = LEGACY_SINGLE_OWNER_ID,
    ) -> bool:
        trade = trade_id if isinstance(trade_id, TradeId) else TradeId(trade_id)
        async with self._session_factory() as session:
            return bool(
                await session.scalar(
                    select(
                        exists().where(
                            TradeORM.id == trade.value,
                            AccountOwnerORM.account_id == TradeORM.account_id,
                            AccountOwnerORM.owner_id == owner_id.value,
                        )
                    )
                )
            )
