"""L3 account-wide read-only discovery above the existing normalized Bybit adapter."""

from __future__ import annotations

import time
from typing import Callable

from terminal.application.trading_accounts import (
    TradingAccountEnvironment, TradingAccountManager, TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import TradingAccountId
from terminal.exchange.bybit_account_validation import BybitAccountValidator
from terminal.exchange.bybit_v5_adapter import BybitCredentials, BybitV5ReadAdapter
from terminal.persistence.credential_store import StoredBybitAccount
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot


class LiveAccountReconciliationError(RuntimeError):
    pass


class LiveAccountReconciler:
    def __init__(
        self, manager: TradingAccountManager, credential_lookup: Callable[[str], StoredBybitAccount],
        validator: BybitAccountValidator, store: LiveAccountProjectionStore,
        *, adapter_factory=BybitV5ReadAdapter, clock_ms=lambda: int(time.time() * 1000),
    ) -> None:
        self._manager = manager
        self._credential_lookup = credential_lookup
        self._validator = validator
        self._store = store
        self._adapter_factory = adapter_factory
        self._clock_ms = clock_ms
        self._generations: dict[str, int] = {}

    def refresh(self, account_id_text: str) -> dict[str, object]:
        account_id = TradingAccountId(account_id_text)
        account = self._manager.account(account_id)
        if account.provider is not TradingAccountProvider.BYBIT:
            raise LiveAccountReconciliationError("bybit_account_required")
        stored = self._credential_lookup(account_id_text)
        current = self._store.get(account_id_text)
        generation = max(self._generations.get(account_id_text, 0), current.refresh_generation if current else 0) + 1
        self._generations[account_id_text] = generation
        session_token = self._manager.session_token
        self._manager.update_status(account_id, TradingAccountStatus.RECONCILING)
        try:
            validated = self._validator.validate(BybitCredentials(stored.api_key, stored.api_secret))
            if validated.environment != stored.environment:
                raise LiveAccountReconciliationError("account_environment_mismatch")
            adapter = self._adapter_factory(
                account_id, BybitCredentials(stored.api_key, stored.api_secret),
                testnet=validated.environment == TradingAccountEnvironment.TESTNET.value,
            )
            wallet = adapter.get_wallet_snapshot()
            positions = adapter.list_open_positions()
            orders = adapter.list_all_active_orders()
            if self._generations.get(account_id_text) != generation or self._manager.session_token != session_token:
                raise LiveAccountReconciliationError("stale_account_refresh")
            now = self._clock_ms()
            snapshot = LiveAccountSnapshot(
                account_id_text, validated.environment, validated.read_only, generation,
                wallet.wallet_balance_usdt, wallet.total_equity_usdt,
                wallet.available_balance_usdt, wallet.exchange_time_ms,
                tuple(_position_projection(account_id_text, item) for item in positions),
                tuple(_order_projection(account_id_text, item) for item in orders), now,
                dict(wallet.balance_provenance),
            )
            self._store.publish(snapshot)
            status = TradingAccountStatus.READ_ONLY if validated.read_only else TradingAccountStatus.READY
            self._manager.update_status(account_id, status)
            return snapshot.transport(status=status.value)
        except Exception as exc:
            if isinstance(exc, LiveAccountReconciliationError) and str(exc) == "stale_account_refresh":
                raise
            self._manager.update_status(account_id, TradingAccountStatus.ERROR)
            if isinstance(exc, LiveAccountReconciliationError):
                raise
            raise LiveAccountReconciliationError("live_account_reconciliation_failed") from exc

    def summary(self, account_id_text: str) -> dict[str, object] | None:
        account = self._manager.account(TradingAccountId(account_id_text))
        snapshot = self._store.get(account_id_text)
        return snapshot.transport(status=account.status.value) if snapshot else None


def _position_projection(account_id: str, item) -> dict[str, object]:
    if item.position_key.trading_account_id != TradingAccountId(account_id):
        raise LiveAccountReconciliationError("cross_account_live_evidence")
    return {
        "account_id": account_id, "symbol": item.position_key.symbol.value,
        "side": item.side.value, "size": str(item.size),
        "average_entry": str(item.average_entry) if item.average_entry is not None else None,
        "mark_price": str(item.mark_price) if item.mark_price is not None else None,
        "unrealized_pnl": str(item.unrealized_pnl) if item.unrealized_pnl is not None else None,
        "updated_at_ms": item.updated_at_ms,
    }


def _order_projection(account_id: str, item) -> dict[str, object]:
    if item.trading_account_id != TradingAccountId(account_id):
        raise LiveAccountReconciliationError("cross_account_live_evidence")
    return {
        "account_id": account_id, "symbol": item.symbol,
        "order_id": item.order_id.value, "side": item.side.value,
        "order_type": item.order_type.value,
        "price": str(item.price) if item.price is not None else None,
        "quantity": str(item.quantity), "status": item.status.value,
        "updated_at_ms": item.updated_at_ms,
    }
