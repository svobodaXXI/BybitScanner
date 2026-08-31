"""Authoritative trading-account selection and session identity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from terminal.domain.models import TradingAccountId


class TradingAccountProvider(str, Enum):
    PAPER = "PAPER"
    BYBIT = "BYBIT"


class TradingAccountEnvironment(str, Enum):
    PAPER = "PAPER"
    MAINNET = "MAINNET"
    TESTNET = "TESTNET"


class TradingAccountStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    VALIDATING = "VALIDATING"
    RECONCILING = "RECONCILING"
    READY = "READY"
    READ_ONLY = "READ_ONLY"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class TradingAccount:
    id: TradingAccountId
    display_name: str
    provider: TradingAccountProvider
    environment: TradingAccountEnvironment
    status: TradingAccountStatus

    def __post_init__(self) -> None:
        if not isinstance(self.id, TradingAccountId):
            raise TypeError("account id must be TradingAccountId")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("account display name must be non-empty")
        object.__setattr__(self, "display_name", self.display_name.strip())
        if not isinstance(self.provider, TradingAccountProvider):
            raise TypeError("account provider must be TradingAccountProvider")
        if not isinstance(self.environment, TradingAccountEnvironment):
            raise TypeError("account environment must be TradingAccountEnvironment")
        if not isinstance(self.status, TradingAccountStatus):
            raise TypeError("account status must be TradingAccountStatus")
        if self.provider is TradingAccountProvider.PAPER:
            if self.environment is not TradingAccountEnvironment.PAPER:
                raise ValueError("PAPER provider requires PAPER environment")
        elif self.environment is TradingAccountEnvironment.PAPER:
            raise ValueError("BYBIT provider requires MAINNET or TESTNET environment")


@dataclass(frozen=True, slots=True)
class AccountSessionToken:
    active_account_id: TradingAccountId
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.active_account_id, TradingAccountId):
            raise TypeError("active account id must be TradingAccountId")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise TypeError("account session generation must be an integer")
        if self.generation < 1:
            raise ValueError("account session generation must be positive")


class TradingAccountManager:
    """Owns the sole active account authority for the current process."""

    def __init__(
        self,
        accounts: Iterable[TradingAccount],
        *,
        active_account_id: TradingAccountId,
        generation: int = 1,
    ) -> None:
        registered: dict[TradingAccountId, TradingAccount] = {}
        for account in accounts:
            if not isinstance(account, TradingAccount):
                raise TypeError("registered account must be TradingAccount")
            if account.id in registered:
                raise ValueError(f"duplicate trading account id: {account.id.value}")
            registered[account.id] = account
        if active_account_id not in registered:
            raise ValueError("active trading account is not registered")
        self._accounts = registered
        self._session_token = AccountSessionToken(active_account_id, generation)

    @property
    def accounts(self) -> tuple[TradingAccount, ...]:
        return tuple(self._accounts.values())

    @property
    def active_account_id(self) -> TradingAccountId:
        return self._session_token.active_account_id

    @property
    def active_account(self) -> TradingAccount:
        return self._accounts[self.active_account_id]

    @property
    def session_token(self) -> AccountSessionToken:
        return self._session_token

    def require_active(self, account_id: TradingAccountId) -> TradingAccount:
        if account_id != self.active_account_id:
            raise RuntimeError("trading account context is not the active account")
        return self.active_account

    def register_inactive(self, account: TradingAccount) -> None:
        if not isinstance(account, TradingAccount):
            raise TypeError("registered account must be TradingAccount")
        if account.id in self._accounts:
            raise ValueError("trading account id is already registered")
        self._accounts[account.id] = account

    def catalog_projection(self) -> dict[str, object]:
        """Return the credential-free, read-only transport account catalog."""
        return {
            "active_account_id": self.active_account_id.value,
            "session_generation": self.session_token.generation,
            "accounts": [
                {
                    "id": account.id.value,
                    "display_name": account.display_name,
                    "provider": account.provider.value,
                    "environment": account.environment.value,
                    "status": account.status.value,
                }
                for account in self.accounts
            ],
        }


def paper_account_manager() -> TradingAccountManager:
    account_id = TradingAccountId("paper")
    return TradingAccountManager(
        (
            TradingAccount(
                id=account_id,
                display_name="Paper / Virtual",
                provider=TradingAccountProvider.PAPER,
                environment=TradingAccountEnvironment.PAPER,
                status=TradingAccountStatus.READY,
            ),
        ),
        active_account_id=account_id,
        generation=1,
    )
