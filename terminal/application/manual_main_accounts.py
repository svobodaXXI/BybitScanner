"""Isolated manual MAIN account inventory; no PAPER runtime, Robot or order dispatch.

This is the application boundary for a future owner-authenticated LIVE service.
It deliberately exposes no mutation/HTTP listener. Deployment and trading gates
remain separate decisions; it is not a second instance of PaperRuntime.
"""
from __future__ import annotations

import hmac
from threading import RLock
from uuid import uuid4

from terminal.application.live_account_reconciliation import LiveAccountReconciler
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import TradingAccountId
from terminal.exchange.bybit_account_validation import BybitAccountValidator
from terminal.exchange.bybit_v5_adapter import BybitCredentials, BybitV5ReadAdapter
from terminal.persistence.credential_store import CredentialStore, StoredBybitAccount
from terminal.persistence.live_account_store import LiveAccountProjectionStore


class ManualMainAccountError(RuntimeError):
    pass


class ManualMainAccounts:
    """Credentials and read-only Bybit snapshots isolated from PAPER ownership."""

    def __init__(
        self, credential_store: CredentialStore,
        snapshot_store: LiveAccountProjectionStore,
        *, validator: BybitAccountValidator | None = None,
        adapter_factory=BybitV5ReadAdapter,
    ) -> None:
        self._lock = RLock()
        self._credentials = credential_store
        self._snapshots = snapshot_store
        self._validator = validator or BybitAccountValidator()
        self._adapter_factory = adapter_factory
        self._stored = list(credential_store.load())
        if any(item.environment != "MAINNET" for item in self._stored):
            raise ManualMainAccountError("manual_main_requires_mainnet")
        self._manager = None
        self._reconciler = None
        if self._stored:
            self._initialize_accounts()

    def _initialize_accounts(self) -> None:
        accounts = tuple(
            TradingAccount(
                TradingAccountId(record.id), record.display_name,
                TradingAccountProvider.BYBIT, TradingAccountEnvironment.MAINNET,
                TradingAccountStatus.DISCONNECTED,
            )
            for record in self._stored
        )
        self._manager = TradingAccountManager(
            accounts, active_account_id=accounts[0].id,
        )
        self._reconciler = LiveAccountReconciler(
            self._manager, self._lookup, self._validator, self._snapshots,
            adapter_factory=self._adapter_factory,
        )

    def _lookup(self, account_id: str) -> StoredBybitAccount:
        for account in self._stored:
            if hmac.compare_digest(account.id, account_id):
                return account
        raise LookupError("unknown_manual_main_account")

    def catalog(self) -> dict[str, object]:
        with self._lock:
            return {
                "accounts": [
                    {"id": a.id, "display_name": a.display_name,
                     "provider": "BYBIT", "environment": a.environment,
                     "status": self._manager.account(TradingAccountId(a.id)).status.value}
                    for a in self._stored
                ],
            }

    def provision(self, display_name: str, api_key: str, api_secret: str) -> dict[str, object]:
        """Validate signed read-only identity, then persist only encrypted credentials.

        Never returns keys or a writable capability; no order API exists here.
        """
        if any(not isinstance(value, str) or not value.strip()
               for value in (display_name, api_key, api_secret)):
            raise ValueError("invalid_main_account_payload")
        display_name = display_name.strip()
        api_key, api_secret = api_key.strip(), api_secret.strip()
        if len(display_name) > 64:
            raise ValueError("invalid_main_account_name")
        with self._lock:
            for existing in self._stored:
                if hmac.compare_digest(existing.api_key, api_key):
                    if not hmac.compare_digest(existing.api_secret, api_secret):
                        raise ManualMainAccountError("duplicate_api_key")
                    return {"account_id": existing.id, "created": False}
            validated = self._validator.validate(BybitCredentials(api_key, api_secret))
            if validated.environment != "MAINNET":
                raise ManualMainAccountError("manual_main_requires_mainnet")
            account = StoredBybitAccount(
                "bybit-" + uuid4().hex, display_name, "MAINNET",
                api_key, api_secret, validated.read_only,
            )
            self._credentials.save(tuple((*self._stored, account)))
            self._stored.append(account)
            if self._manager is None:
                self._initialize_accounts()
            else:
                self._manager.register_inactive(TradingAccount(
                    TradingAccountId(account.id), display_name,
                    TradingAccountProvider.BYBIT, TradingAccountEnvironment.MAINNET,
                    TradingAccountStatus.DISCONNECTED,
                ))
            return {"account_id": account.id, "created": True}

    def refresh(self, account_id: str) -> dict[str, object]:
        """Only V5 account validation, wallet, positions and active-order reads."""
        with self._lock:
            self._lookup(account_id)
            if self._reconciler is None:
                raise ManualMainAccountError("manual_main_unconfigured")
            return self._reconciler.refresh(account_id)

    def summary(self, account_id: str) -> dict[str, object] | None:
        with self._lock:
            self._lookup(account_id)
            if self._reconciler is None:
                raise ManualMainAccountError("manual_main_unconfigured")
            return self._reconciler.summary(account_id)

    def close(self) -> None:
        self._snapshots.close()
