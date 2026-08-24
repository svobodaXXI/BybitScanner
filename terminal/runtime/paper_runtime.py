"""Composed local PAPER trading runtime for the development Workspace."""

from __future__ import annotations

import time
import hashlib
from decimal import Decimal
from pathlib import Path

from terminal.api.rest import TerminalCommandApi
from terminal.api.models import (
    CommandResultStatus, LimitCommandRequest, PaperLimitCancelRequest,
    PaperLimitMutationResult, PaperLimitOrderProjection, TimeInForce,
)
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.pretrade_guard import MutationGate, PreTradeGuard
from terminal.application.pretrade_guard import NotionalIntent, OrderKind, PreTradeIntent
from terminal.application.pretrade_guard import WorkingVolumeIntent
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import Category, Price, Quantity, Symbol, TradingAccountId
from terminal.domain.models import OrderId
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.executor import PaperMarketExecutor
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_context import (
    PaperCommandContextProvider,
    working_volume_usdt,
)


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


class DevelopmentBookProvider:
    """Fresh normalized development book until live Market Data Engine is wired."""

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        if symbol.value != "BTCUSDT":
            return None

        return NormalizedOrderBook(
            symbol=symbol,
            bids=(
                PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("0.8"))),
                PriceLevel(Price(Decimal("64249.0")), Quantity(Decimal("4.2"))),
                PriceLevel(Price(Decimal("64248.5")), Quantity(Decimal("3.8"))),
            ),
            asks=(
                PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("3.0"))),
                PriceLevel(Price(Decimal("64251.0")), Quantity(Decimal("2.6"))),
                PriceLevel(Price(Decimal("64251.5")), Quantity(Decimal("2.2"))),
            ),
            health=BookHealth.READY,
            received_at_ms=int(time.time() * 1000),
            available_depth=3,
        )


def instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR,
        "BTCUSDT",
        "LinearPerpetual",
        "Trading",
        "BTC",
        "USDT",
        "USDT",
        Decimal("0.5"),
        Decimal("1000000"),
        Decimal("0.5"),
        Decimal("0.001"),
        Decimal("100"),
        Decimal("50"),
        Decimal("0.001"),
        Decimal("5"),
    )


class PaperRuntime:
    def __init__(self, database_path: Path) -> None:
        self.store = SQLiteStore.open(database_path)
        engine = ExecutionEngine(self.store)
        book_provider = DevelopmentBookProvider()

        paper_executor = PaperMarketExecutor(
            book_provider,
            engine,
            max_book_age_ms=1000,
            fee_rate=Decimal("0.0006"),
            clock_ms=lambda: int(time.time() * 1000),
        )

        account_id = TradingAccountId("paper")
        self.store.initialize_paper_account(
            account_id,
            Decimal("5000"),
            updated_at_ms=int(time.time() * 1000),
        )

        context_provider = PaperCommandContextProvider(
            store=self.store,
            account_id=account_id,
            instrument=instrument(),
        )

        application = TradingApplication(
            PreTradeGuard(gate=MutationGate(mutations_enabled=True)),
            self.store,
            PaperOnlyAdapter(),
            engine,
            mutations_enabled=True,
            clock_ms=lambda: int(time.time() * 1000),
            paper_market_executor=paper_executor,
        )

        self.api = TerminalCommandApi(application, context_provider)
        self._guard = application.guard
        self._context = context_provider
        self._account_id = account_id

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
        if position_quantity == 0:
            position_quantity = Decimal("0")
            engaged_notional = Decimal("0")

        return {
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
                for item in self.store.load_active_paper_limits(Symbol(normalized_symbol))
            ],
        }

    def create_limit(self, request: LimitCommandRequest) -> PaperLimitMutationResult:
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
        symbol = request.symbol.strip().upper()
        if symbol != "BTCUSDT":
            raise ValueError("unsupported PAPER symbol")
        existing = self.store.get_paper_limit(request.order_id)
        if existing is not None and existing.symbol.value != symbol:
            raise ValueError("order symbol does not match")
        fingerprint = _fingerprint(symbol, request.order_id)
        order, changed = self.store.cancel_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=fingerprint,
            order_id=OrderId(request.order_id),
            updated_at_ms=int(time.time() * 1000),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "cancelled" if changed and order is not None and order.status == "cancelled" else "already_absent",
            request.order_id,
        )

    def close(self) -> None:
        self.store.close()


def _fingerprint(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()
