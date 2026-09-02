"""Composed local PAPER trading runtime for the development Workspace."""

from __future__ import annotations

import time
import hashlib
import hmac
import logging
from uuid import uuid4
from decimal import Decimal
from pathlib import Path
from typing import Callable

from terminal.api.rest import TerminalCommandApi
from terminal.api.models import (
    ClientActionId, CloseAllCommandRequest, CloseAllCommandResponse, CommandResultStatus,
    FullCloseCommandRequest, LimitCommandRequest, PaperLimitAmendRequest, PaperLimitCancelRequest,
    PaperLimitMutationResult, PaperLimitOrderProjection, PaperOpenPositionProjection,
    PaperOpenPositionsResponse, PaperStopDeleteRequest, PaperStopMutationRequest,
    PaperStopMutationResult, TimeInForce, to_primitive,
    LiveMarketCommandRequest,
)
from terminal.application.live_market_execution import LiveMarketMutationCoordinator, LiveMarketMutationGates
from terminal.api.projections import project_protection
from terminal.application.protection import normalize_paper_protection_trigger
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.pretrade_guard import MutationGate, PreTradeGuard
from terminal.application.normalization import normalize_limit_price
from terminal.application.pretrade_guard import NotionalIntent, OrderKind, PreTradeIntent
from terminal.application.pretrade_guard import WorkingVolumeIntent
from terminal.application.trading_application import TradingApplication
from terminal.application.trading_accounts import (
    TradingAccount,
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
    paper_account_manager,
)
from terminal.application.live_account_reconciliation import LiveAccountReconciler
from terminal.domain.models import (
    ExecutionId, OrderId, OrderSide, PositionSide, Quantity, Symbol,
    TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.exchange.bybit_account_validation import BybitAccountValidator
from terminal.exchange.bybit_v5_adapter import BybitCredentials, BybitV5ReadAdapter
from terminal.exchange.bybit_v5_mutation_adapter import BybitEnvironment, BybitV5MutationAdapter
from terminal.market_data.book_provider import MarketBookProvider
from terminal.paper.executor import PaperLimitExecutor, PaperMarketExecutor
from terminal.persistence.sqlite_store import ExecutionApplyResult, SQLiteStore
from terminal.persistence.credential_store import DpapiCredentialStore, StoredBybitAccount
from terminal.persistence.live_account_store import LiveAccountProjectionStore
from terminal.persistence.active_account_preference import (
    ActiveAccountPreferenceError, ActiveAccountPreferenceStore,
)
from terminal.runtime.paper_context import (
    PaperCommandContextProvider,
    working_volume_usdt,
)


LOGGER = logging.getLogger(__name__)


class PaperOnlyAdapter:
    """Fail closed if any non-PAPER mutation path is reached."""

    def _blocked(self):
        raise RuntimeError("live exchange mutations are unavailable in PAPER runtime")

    def create_market_order(self, **kwargs):
        self._blocked()

    def create_limit_order(self, **kwargs):
        self._blocked()

    def amend_order(self, **kwargs):
        self._blocked()

    def cancel_order(self, **kwargs):
        self._blocked()

    def set_trading_stop(self, **kwargs):
        self._blocked()


class PaperRuntime:
    def __init__(
        self,
        database_path: Path,
        *,
        book_provider: MarketBookProvider,
        instrument_snapshot: InstrumentSnapshot,
        instrument_provider: Callable[[str], InstrumentSnapshot] | None = None,
        account_manager: TradingAccountManager | None = None,
        credential_store: DpapiCredentialStore | None = None,
        account_validator: BybitAccountValidator | None = None,
        live_account_store: LiveAccountProjectionStore | None = None,
        active_account_preference_store: ActiveAccountPreferenceStore | None = None,
        live_adapter_factory=None,
        live_mutation_adapter_factory=BybitV5MutationAdapter,
        live_market_mutations_enabled: bool = False,
        live_mainnet_authorized: bool = False,
        live_acceptance_notional_ceiling: Decimal = Decimal("0"),
    ) -> None:
        self._account_manager = account_manager or paper_account_manager()
        self._paper_account_id = TradingAccountId("paper")
        self._credential_store = credential_store
        self._account_validator = account_validator
        self._live_account_store = live_account_store
        self._active_account_preference_store = active_account_preference_store
        self._live_market_mutations_enabled = live_market_mutations_enabled
        self._live_mainnet_authorized = live_mainnet_authorized
        self._instrument_provider = instrument_provider or (lambda _symbol: instrument_snapshot)
        self._stored_bybit_accounts = list(credential_store.load()) if credential_store else []
        for stored in self._stored_bybit_accounts:
            self._account_manager.register_inactive(TradingAccount(
                TradingAccountId(stored.id), stored.display_name,
                TradingAccountProvider.BYBIT, TradingAccountEnvironment(stored.environment),
                TradingAccountStatus.DISCONNECTED,
            ))
        self._live_account_reconciler = (
            LiveAccountReconciler(
                self._account_manager,
                self._stored_bybit_account,
                account_validator,
                live_account_store,
                **({"adapter_factory": live_adapter_factory} if live_adapter_factory else {}),
            )
            if credential_store and account_validator and live_account_store
            else None
        )
        active_account = self._account_manager.active_account
        if (
            active_account.provider is not TradingAccountProvider.PAPER
            or active_account.environment is not TradingAccountEnvironment.PAPER
            or active_account.id != TradingAccountId("paper")
        ):
            raise RuntimeError("PAPER runtime requires the authoritative paper account")
        account_id = self._paper_account_id

        self.store = SQLiteStore.open(database_path)
        engine = ExecutionEngine(self.store)
        self._book_provider = book_provider
        self._limit_executor = PaperLimitExecutor(
            engine,
            fee_rate=Decimal("0.0006"),
            clock_ms=lambda: int(time.time() * 1000),
        )
        self._last_processed_book_update_id: str | None = None

        self._market_executor = PaperMarketExecutor(
            book_provider,
            engine,
            max_book_age_ms=1000,
            fee_rate=Decimal("0.0006"),
            clock_ms=lambda: int(time.time() * 1000),
        )

        self.store.initialize_paper_account(
            account_id,
            Decimal("5000"),
            updated_at_ms=int(time.time() * 1000),
        )

        context_provider = PaperCommandContextProvider(
            store=self.store,
            account_id=account_id,
            instrument=instrument_snapshot,
            instrument_provider=instrument_provider,
            active_account_id_provider=lambda: self._account_manager.active_account_id,
        )

        application = TradingApplication(
            PreTradeGuard(gate=MutationGate(mutations_enabled=True)),
            self.store,
            PaperOnlyAdapter(),
            engine,
            mutations_enabled=True,
            clock_ms=lambda: int(time.time() * 1000),
            paper_market_executor=self._market_executor,
        )

        self.api = TerminalCommandApi(application, context_provider)
        self._live_market = LiveMarketMutationCoordinator(
            self._account_manager, self.store,
            lambda account_id: live_mutation_adapter_factory(
                BybitCredentials(
                    self._stored_bybit_account(account_id.value).api_key,
                    self._stored_bybit_account(account_id.value).api_secret,
                ),
                environment=BybitEnvironment.MAINNET,
                mutations_enabled=live_market_mutations_enabled,
                live_authorized=live_mainnet_authorized,
            ),
            instrument_provider=self._instrument_provider,
            book_provider=self._book_provider,
            writable_account_provider=self._is_stored_account_writable,
            read_adapter_provider=lambda account_id: (live_adapter_factory or BybitV5ReadAdapter)(
                account_id,
                BybitCredentials(
                    self._stored_bybit_account(account_id.value).api_key,
                    self._stored_bybit_account(account_id.value).api_secret,
                ),
                testnet=False,
            ),
            projection_refresher=(
                self._live_account_reconciler.refresh
                if self._live_account_reconciler is not None else None
            ),
            gates=LiveMarketMutationGates(
                live_market_mutations_enabled, live_mainnet_authorized,
                live_acceptance_notional_ceiling,
            ),
        )
        self._guard = application.guard
        self._context = context_provider
        self._restore_preferred_account()
        self._live_market.recover_unresolved()

    @property
    def _account_id(self) -> TradingAccountId:
        """Immutable PAPER persistence identity, independent of active session authority."""
        return self._paper_account_id

    def account_catalog(self) -> dict[str, object]:
        return self._account_manager.catalog_projection()

    def _stored_bybit_account(self, account_id: str) -> StoredBybitAccount:
        for stored in self._stored_bybit_accounts:
            if hmac.compare_digest(stored.id, account_id):
                return stored
        raise LookupError("stored Bybit account is unavailable")

    def refresh_live_account(self, account_id: str) -> dict[str, object]:
        if self._live_account_reconciler is None:
            raise RuntimeError("live_account_reconciliation_unavailable")
        snapshot = self._live_account_reconciler.refresh(account_id)
        self._live_market.recover_unresolved(TradingAccountId(account_id))
        return snapshot

    def live_account_summary(self, account_id: str) -> dict[str, object] | None:
        if self._live_account_reconciler is None:
            raise RuntimeError("live_account_reconciliation_unavailable")
        return self._live_account_reconciler.summary(account_id)

    def activate_account(self, account_id_text: str) -> dict[str, object]:
        account_id = TradingAccountId(account_id_text)
        target = self._account_manager.account(account_id)
        if not self._account_manager.is_activation_eligible(account_id):
            raise RuntimeError("account_activation_not_ready")
        if target.provider is TradingAccountProvider.BYBIT:
            if self._live_account_store is None:
                raise RuntimeError("live_account_snapshot_unavailable")
            snapshot = self._live_account_store.get(account_id_text)
            if (
                snapshot is None
                or snapshot.environment != target.environment.value
                or snapshot.read_only != (target.status is TradingAccountStatus.READ_ONLY)
            ):
                raise RuntimeError("live_account_snapshot_unavailable")
        if self._active_account_preference_store is not None:
            self._active_account_preference_store.save(account_id)
        token = self._account_manager.activate(account_id)
        return {
            "active_account_id": token.active_account_id.value,
            "session_generation": token.generation,
            "status": target.status.value,
        }

    def _restore_preferred_account(self) -> None:
        store = self._active_account_preference_store
        if store is None:
            return
        try:
            preferred = store.load()
            if preferred is None:
                LOGGER.info("account_restore no_preference path=%s active=paper", store.path)
                return
            LOGGER.info(
                "account_restore preference_loaded account_id=%s path=%s",
                preferred.value, store.path,
            )
            if preferred == self._paper_account_id:
                LOGGER.info("account_restore paper_preference active=paper generation=1")
                return
            target = self._account_manager.account(preferred)
            if target.provider is not TradingAccountProvider.BYBIT:
                LOGGER.warning("account_restore fallback=paper reason=preferred_provider_not_bybit")
                return
            if self._live_account_reconciler is None:
                LOGGER.warning("account_restore fallback=paper reason=reconciliation_unavailable")
                return
            LOGGER.info("account_restore reconnect_started account_id=%s", preferred.value)
            snapshot = self._live_account_reconciler.refresh(preferred.value)
            LOGGER.info(
                "account_restore snapshot_ready account_id=%s status=%s refresh_generation=%s",
                preferred.value, snapshot["status"], snapshot["refresh_generation"],
            )
            activated = self.activate_account(preferred.value)
            LOGGER.info(
                "account_restore activation_success account_id=%s status=%s session_generation=%s",
                preferred.value, activated["status"], activated["session_generation"],
            )
        except (ActiveAccountPreferenceError, LookupError, RuntimeError) as exc:
            # Startup restoration is best effort and fail-closed: PAPER remains authority.
            LOGGER.warning(
                "account_restore fallback=paper reason=%s",
                str(exc) or type(exc).__name__,
            )
            return

    def workspace_account_projection(self, symbol: str) -> dict[str, object]:
        account = self._account_manager.active_account
        token = self._account_manager.session_token
        envelope: dict[str, object] = {
            "account_id": account.id.value,
            "provider": account.provider.value,
            "environment": account.environment.value,
            "status": account.status.value,
            "session_generation": token.generation,
            "read_only": False,
            "capabilities": {
                "market": account.provider is TradingAccountProvider.PAPER,
                "limit": account.provider is TradingAccountProvider.PAPER,
                "stop": account.provider is TradingAccountProvider.PAPER,
                "take": account.provider is TradingAccountProvider.PAPER,
                "full_close": account.provider is TradingAccountProvider.PAPER,
            },
        }
        if account.provider is TradingAccountProvider.PAPER:
            state = self.paper_state(symbol)
            positions = to_primitive(self.open_positions()).get("positions", [])
            return {
                **envelope,
                "projection_generation": state["state_revision"],
                "wallet_balance_usdt": state["equity_usdt"],
                "total_equity_usdt": state["equity_usdt"],
                "available_balance_usdt": state["equity_usdt"],
                "positions": positions,
                "orders": state["active_limit_orders"],
                "paper_state": state,
            }
        if self._live_account_store is None:
            raise RuntimeError("live_account_snapshot_unavailable")
        snapshot = self._live_account_store.get(account.id.value)
        if snapshot is None or snapshot.environment != account.environment.value:
            raise RuntimeError("live_account_snapshot_unavailable")
        return {
            **envelope,
            "read_only": snapshot.read_only,
            "capabilities": {
                "market": bool(
                    not snapshot.read_only
                    and account.environment is TradingAccountEnvironment.MAINNET
                    and account.status is TradingAccountStatus.READY
                    and self._live_market_mutations_enabled
                    and self._live_mainnet_authorized
                ),
                "limit": False, "stop": False, "take": False, "full_close": False,
            },
            "projection_generation": snapshot.refresh_generation,
            "wallet_balance_usdt": str(snapshot.wallet_balance_usdt),
            "total_equity_usdt": str(snapshot.total_equity_usdt),
            "available_balance_usdt": str(snapshot.available_balance_usdt),
            "positions": list(snapshot.positions),
            "orders": list(snapshot.orders),
            "paper_state": None,
            "balance_source_fields": {
                "wallet_balance_usdt": "result.list[0].totalWalletBalance",
                "total_equity_usdt": "result.list[0].totalEquity",
                "available_balance_usdt": "result.list[0].totalEquity",
                "account_type": "UNIFIED",
                "unit": "USD",
            },
            "balance_provenance": dict(snapshot.balance_provenance or {}),
        }

    def require_paper_mutations(self) -> None:
        active = self._account_manager.active_account
        if not (
            active.provider is TradingAccountProvider.PAPER
            and active.environment is TradingAccountEnvironment.PAPER
            and active.status is TradingAccountStatus.READY
        ):
            raise RuntimeError("live_mutations_disabled")

    def market(self, request):
        self.require_paper_mutations()
        return self.api.market(request)

    def live_market(self, request: LiveMarketCommandRequest):
        return self._live_market.submit(request)

    def _is_stored_account_writable(self, account_id: TradingAccountId) -> bool:
        stored = self._stored_bybit_account(account_id.value)
        return stored.environment == TradingAccountEnvironment.MAINNET.value and not stored.read_only

    def full_close(self, request):
        self.require_paper_mutations()
        return self.api.full_close(request)

    def add_bybit_account(self, display_name: str, api_key: str, api_secret: str) -> dict[str, object]:
        if not self._credential_store or not self._account_validator:
            raise RuntimeError("account_provisioning_unavailable")
        if not all(isinstance(value, str) and value.strip() for value in (display_name, api_key, api_secret)):
            raise ValueError("invalid_account_payload")
        display_name, api_key, api_secret = display_name.strip(), api_key.strip(), api_secret.strip()
        for stored in self._stored_bybit_accounts:
            if hmac.compare_digest(stored.api_key, api_key) and hmac.compare_digest(stored.api_secret, api_secret):
                return {"account_id": stored.id, "created": False}
        validated = self._account_validator.validate(BybitCredentials(api_key, api_secret))
        account_id = f"bybit-{uuid4().hex}"
        stored = StoredBybitAccount(
            account_id, display_name, validated.environment, api_key, api_secret,
            validated.read_only,
        )
        updated = (*self._stored_bybit_accounts, stored)
        self._credential_store.save(updated)
        self._account_manager.register_inactive(TradingAccount(
            TradingAccountId(account_id), display_name, TradingAccountProvider.BYBIT,
            TradingAccountEnvironment(validated.environment),
            TradingAccountStatus.READ_ONLY if validated.read_only else TradingAccountStatus.READY,
        ))
        self._stored_bybit_accounts.append(stored)
        return {"account_id": account_id, "created": True}

    def process_orderbook_update(self, notified_book_update_id: str) -> int:
        if not notified_book_update_id:
            raise ValueError("book_update_id must be non-empty")
        active_account = self._account_manager.active_account
        if not (
            active_account.id == self._paper_account_id
            and active_account.provider is TradingAccountProvider.PAPER
            and active_account.environment is TradingAccountEnvironment.PAPER
            and active_account.status is TradingAccountStatus.READY
        ):
            return 0
        notified_symbol = notified_book_update_id.split(":", 1)[0].strip().upper()
        if not notified_symbol:
            return 0
        current_update = self._book_provider.get_current_book_update(Symbol(notified_symbol))
        if current_update is None:
            return 0
        book_update_id, book = current_update
        if book_update_id == self._last_processed_book_update_id:
            return 0

        # Claim the authoritative snapshot before applying its orders. A queued
        # duplicate therefore cannot replay fills if one order raises midway.
        self._last_processed_book_update_id = book_update_id
        applied = 0
        for order in self.store.load_active_paper_limits(self._account_id, book.symbol):
            result = self._limit_executor.execute(
                order=order,
                book=book,
                match_event_id=book_update_id,
            )
            if result is not None and result.apply_result is ExecutionApplyResult.APPLIED:
                applied += 1
        context = self._context.context_for(book.symbol.value)
        protection = self.store.get_protection_projection(
            context.pretrade.position_key
        )
        if protection is None or (
            protection.stop_loss is None and protection.take_profit is None
        ):
            return applied
        position = self.store.get_position_projection(context.pretrade.position_key)
        if position is None or (
            position.side is PositionSide.FLAT or position.quantity.value == 0
        ):
            self.store.clear_paper_protection_for_flat(context.pretrade.position_key)
            return applied

        exit_market = (
            book.bids[0].price.value
            if position.side is PositionSide.LONG
            else book.asks[0].price.value
        )
        stop_triggered = protection.stop_loss is not None and (
            exit_market <= protection.stop_loss
            if position.side is PositionSide.LONG
            else exit_market >= protection.stop_loss
        )
        take_triggered = protection.take_profit is not None and (
            exit_market >= protection.take_profit
            if position.side is PositionSide.LONG
            else exit_market <= protection.take_profit
        )
        leg = "stop" if stop_triggered else "take" if take_triggered else None
        if leg is None:
            return applied

        digest = hashlib.sha256(
            (
                f"{context.pretrade.position_key.symbol.value}\0{protection.version}"
                f"\0{book_update_id}"
            ).encode("utf-8")
        ).hexdigest()
        side = (
            OrderSide.SELL
            if position.side is PositionSide.LONG
            else OrderSide.BUY
        )
        stop_result = self._market_executor.execute(
            trading_account_id=context.pretrade.position_key.trading_account_id,
            symbol=context.pretrade.position_key.symbol,
            side=side,
            quantity=Quantity(position.quantity.value),
            order_link_id=f"paper-{leg}-{digest}",
            order_id=OrderId(f"paper-{leg}-order-{digest}"),
            exec_id=ExecutionId(f"paper-{leg}-exec-{digest}"),
        )
        if stop_result.apply_result is ExecutionApplyResult.APPLIED:
            applied += 1
        return applied

    def paper_state(self, symbol: str) -> dict[str, object]:
        normalized_symbol = symbol.strip().upper()
        context = self.api._context.context_for(normalized_symbol)

        account_id = context.pretrade.selected_account_id
        account = self.store.get_paper_account(account_id)
        if account is None:
            raise ValueError("paper account is not initialized")

        projection = self.store.get_position_projection(
            context.pretrade.position_key
        )
        one_wv = working_volume_usdt(account.equity_usdt)
        engaged_notional = (
            projection.engaged_notional.value
            if projection is not None
            else Decimal("0")
        )
        position_quantity = (
            projection.quantity.value if projection is not None else Decimal("0")
        )
        average_entry = (
            projection.average_entry.value
            if projection is not None and projection.average_entry is not None
            else None
        )
        if position_quantity == 0:
            position_quantity = Decimal("0")
            engaged_notional = Decimal("0")
            average_entry = None
        protection = project_protection(
            self.store.get_protection_projection(context.pretrade.position_key)
        )
        protection_projection = to_primitive(protection)
        protection_projection["effective_quantity"] = (
            str(position_quantity)
            if (protection.stop_loss is not None or protection.take_profit is not None)
            and position_quantity > 0
            else None
        )

        return {
            "state_revision": self.store.get_paper_state_revision(
                account_id, Symbol(normalized_symbol),
            ),
            "account_id": account.trading_account_id.value,
            "symbol": normalized_symbol,
            "initial_deposit_usdt": str(account.initial_deposit_usdt),
            "equity_usdt": str(account.equity_usdt),
            "one_wv_usdt": str(one_wv),
            "position_side": (
                projection.side.value if projection is not None else "Flat"
            ),
            "position_quantity": (
                str(position_quantity)
            ),
            "average_entry": str(average_entry) if average_entry is not None else None,
            "engaged_notional_usdt": str(engaged_notional),
            "engaged_wv": (
                "0.0" if engaged_notional == 0 else str(engaged_notional / one_wv)
            ),
            "active_limit_orders": [
                {
                    "order_id": item.order_id.value,
                    "order_link_id": item.order_link_id,
                    "symbol": item.symbol.value,
                    "side": item.side.value,
                    "price": str(item.price),
                    "quantity": str(item.quantity),
                    "time_in_force": TimeInForce.GTC.value,
                }
                for item in self.store.load_active_paper_limits(
                    account_id, Symbol(normalized_symbol),
                )
            ],
            "protection": protection_projection,
        }

    def open_positions(self) -> PaperOpenPositionsResponse:
        account = self.store.get_paper_account(self._account_id)
        if account is None:
            raise ValueError("paper account is not initialized")
        one_wv = working_volume_usdt(account.equity_usdt)
        projected = []
        for item in self.store.load_open_position_projections(self._account_id):
            symbol = item.position_key.symbol
            instrument = self._context._instrument_for(symbol.value)
            book = self._book_provider.get_book(symbol)
            now_ms = int(time.time() * 1000)
            current_price = None
            unrealized_pnl = None
            if (
                book is not None
                and book.symbol == symbol
                and 0 <= now_ms - book.received_at_ms <= 1000
                and book.bids
                and book.asks
            ):
                current_price = (
                    book.bids[0].price.value + book.asks[0].price.value
                ) / Decimal("2")
                if item.average_entry is not None:
                    direction = Decimal("1") if item.side.value == "Long" else Decimal("-1")
                    unrealized_pnl = (
                        direction
                        * (current_price - item.average_entry.value)
                        * item.quantity.value
                    )
            projected.append(PaperOpenPositionProjection(
                symbol=item.position_key.symbol.value,
                position_side=item.side.value,
                position_quantity=item.quantity.value,
                average_entry=(
                    item.average_entry.value
                    if item.average_entry is not None
                    else None
                ),
                engaged_notional_usdt=item.engaged_notional.value,
                engaged_wv=item.engaged_notional.value / one_wv,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                tick_size=instrument.tick_size,
            ))
        return PaperOpenPositionsResponse(account.trading_account_id.value, tuple(projected))

    def close_all(self, request: CloseAllCommandRequest) -> CloseAllCommandResponse:
        self.require_paper_mutations()
        source_positions = self.store.load_open_position_projections(self._account_id)
        results = []
        for position in source_positions:
            symbol = position.position_key.symbol.value
            digest = hashlib.sha256(
                f"{request.client_action_id.value}\0{symbol}".encode("utf-8")
            ).hexdigest()[:32]
            results.append(self.api.full_close(FullCloseCommandRequest(
                ClientActionId(f"paper-close-all-{digest}"), symbol,
            )))
        refreshed = self.open_positions()
        return CloseAllCommandResponse(
            request.client_action_id.value, tuple(results), refreshed.positions,
        )

    def create_limit(self, request: LimitCommandRequest) -> PaperLimitMutationResult:
        self.require_paper_mutations()
        symbol = request.symbol.strip().upper()
        if request.time_in_force is not TimeInForce.GTC:
            raise ValueError("PAPER Limit supports GTC only")
        context = self._context.context_for(symbol)
        volume = (
            NotionalIntent(request.volume.amount)
            if request.volume.unit.value == "usdt"
            else WorkingVolumeIntent(request.volume.amount, context.one_wv_usdt)
        )
        decision = self._guard.evaluate(
            PreTradeIntent(
                symbol, request.side, OrderKind.LIMIT, volume,
                request.sizing_reference_price, request.limit_price,
            ),
            context.pretrade,
        )
        if not decision.admitted:
            code = decision.reason_code.value if decision.reason_code else "blocked"
            return PaperLimitMutationResult(
                request.client_action_id.value, CommandResultStatus.BLOCKED, code, None,
            )
        admitted = decision.request
        assert admitted is not None and admitted.normalized_limit_price is not None
        fingerprint = _fingerprint(
            symbol, request.side.value, str(request.volume.amount), request.volume.unit.value,
            str(admitted.normalized_limit_price), request.time_in_force.value,
        )
        order_id = OrderId(f"paper-limit-{admitted.identity.order_link_id}")
        order, created = self.store.create_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            order_id=order_id,
            order_link_id=admitted.identity.order_link_id,
            trading_account_id=self._account_id,
            symbol=Symbol(symbol), side=request.side,
            price=admitted.normalized_limit_price,
            quantity=admitted.final_quantity,
            created_at_ms=int(time.time() * 1000),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "created" if created else "duplicate_action", order.order_id.value,
        )

    def cancel_limit(self, request: PaperLimitCancelRequest) -> PaperLimitMutationResult:
        self.require_paper_mutations()
        symbol = request.symbol.strip().upper()
        if symbol != self._context.instrument.symbol:
            raise ValueError("unsupported PAPER symbol")
        existing = self.store.get_paper_limit(request.order_id, self._account_id)
        if existing is not None and existing.symbol.value != symbol:
            raise ValueError("order symbol does not match")
        fingerprint = _fingerprint(symbol, request.order_id)
        order, changed = self.store.cancel_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            order_id=OrderId(request.order_id),
            trading_account_id=self._account_id,
            updated_at_ms=int(time.time() * 1000),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "cancelled" if changed and order is not None and order.status == "cancelled" else "already_absent",
            request.order_id,
        )

    def amend_limit(self, request: PaperLimitAmendRequest) -> PaperLimitMutationResult:
        self.require_paper_mutations()
        symbol = request.symbol.strip().upper()
        existing = self.store.get_paper_limit(request.order_id, self._account_id)
        if existing is None or existing.status != "open":
            raise ValueError("PAPER limit is missing or inactive")
        if existing.symbol.value != symbol:
            raise ValueError("order symbol does not match")
        context = self._context.context_for(symbol)
        normalized_price = normalize_limit_price(
            request.limit_price, context.pretrade.instrument.tick_size, existing.side,
        )
        decision = self._guard.evaluate(
            PreTradeIntent(
                symbol, existing.side, OrderKind.LIMIT,
                NotionalIntent(existing.quantity * normalized_price), normalized_price,
                request.limit_price,
            ),
            context.pretrade,
        )
        if not decision.admitted:
            code = decision.reason_code.value if decision.reason_code else "blocked"
            return PaperLimitMutationResult(
                request.client_action_id.value, CommandResultStatus.BLOCKED, code,
                existing.order_id.value,
            )
        admitted = decision.request
        assert admitted is not None and admitted.normalized_limit_price is not None
        fingerprint = _fingerprint(
            symbol, request.order_id, str(admitted.normalized_limit_price),
        )
        amended, changed = self.store.amend_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            order_id=existing.order_id,
            trading_account_id=self._account_id,
            price=admitted.normalized_limit_price,
            updated_at_ms=int(time.time() * 1000),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "amended" if changed else "duplicate_action", amended.order_id.value,
        )

    def create_stop(self, request: PaperStopMutationRequest) -> PaperStopMutationResult:
        return self._mutate_protection("stop", "create", request)

    def amend_stop(self, request: PaperStopMutationRequest) -> PaperStopMutationResult:
        return self._mutate_protection("stop", "amend", request)

    def delete_stop(self, request: PaperStopDeleteRequest) -> PaperStopMutationResult:
        return self._delete_protection("stop", request)

    def create_take(self, request: PaperStopMutationRequest) -> PaperStopMutationResult:
        return self._mutate_protection("take", "create", request)

    def amend_take(self, request: PaperStopMutationRequest) -> PaperStopMutationResult:
        return self._mutate_protection("take", "amend", request)

    def delete_take(self, request: PaperStopDeleteRequest) -> PaperStopMutationResult:
        return self._delete_protection("take", request)

    def _delete_protection(
        self, leg: str, request: PaperStopDeleteRequest,
    ) -> PaperStopMutationResult:
        self.require_paper_mutations()
        symbol = request.symbol.strip().upper()
        context = self._context.context_for(symbol)
        fingerprint = _fingerprint(symbol, "delete") if leg == "stop" else _fingerprint(symbol, leg, "delete")
        _, changed, replayed = self.store.mutate_paper_protection_leg(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            operation="delete",
            position_key=context.pretrade.position_key,
            leg=leg,
            trigger=None,
            updated_at_ms=int(time.time() * 1000),
        )
        return PaperStopMutationResult(
            request.client_action_id.value,
            CommandResultStatus.COMPLETED,
            "duplicate_action" if replayed else "deleted" if changed else "already_absent",
        )

    def _mutate_protection(
        self, leg: str, operation: str, request: PaperStopMutationRequest,
    ) -> PaperStopMutationResult:
        self.require_paper_mutations()
        symbol = request.symbol.strip().upper()
        context = self._context.context_for(symbol)
        normalized = normalize_paper_protection_trigger(
            context.position, context.instrument, request.trigger_price, leg,
        )
        fingerprint = (
            _fingerprint(symbol, operation, str(normalized))
            if leg == "stop"
            else _fingerprint(symbol, leg, operation, str(normalized))
        )
        _, changed, replayed = self.store.mutate_paper_protection_leg(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            operation=operation,
            position_key=context.pretrade.position_key,
            leg=leg,
            trigger=normalized,
            updated_at_ms=int(time.time() * 1000),
        )
        return PaperStopMutationResult(
            request.client_action_id.value,
            CommandResultStatus.COMPLETED,
            ("duplicate_action" if replayed or not changed
             else {"create": "created", "amend": "amended"}[operation]),
        )

    def close(self) -> None:
        self.store.close()
        if self._live_account_store is not None:
            self._live_account_store.close()


def _fingerprint(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()
