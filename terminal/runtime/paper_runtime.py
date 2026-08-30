"""Composed local PAPER trading runtime for the development Workspace."""

from __future__ import annotations

import time
import hashlib
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
)
from terminal.api.projections import project_protection
from terminal.application.protection import normalize_paper_protection_trigger
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.pretrade_guard import MutationGate, PreTradeGuard
from terminal.application.normalization import normalize_limit_price
from terminal.application.pretrade_guard import NotionalIntent, OrderKind, PreTradeIntent
from terminal.application.pretrade_guard import WorkingVolumeIntent
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import (
    ExecutionId, OrderId, OrderSide, PositionSide, Quantity, Symbol,
    TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.book_provider import MarketBookProvider
from terminal.paper.executor import PaperLimitExecutor, PaperMarketExecutor
from terminal.persistence.sqlite_store import ExecutionApplyResult, SQLiteStore
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


class PaperRuntime:
    def __init__(
        self,
        database_path: Path,
        *,
        book_provider: MarketBookProvider,
        instrument_snapshot: InstrumentSnapshot,
        instrument_provider: Callable[[str], InstrumentSnapshot] | None = None,
    ) -> None:
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

        account_id = TradingAccountId("paper")
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
        self._guard = application.guard
        self._context = context_provider
        self._account_id = account_id

    def process_orderbook_update(self, notified_book_update_id: str) -> int:
        if not notified_book_update_id:
            raise ValueError("book_update_id must be non-empty")
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
        for order in self.store.load_active_paper_limits(book.symbol):
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
                for item in self.store.load_active_paper_limits(Symbol(normalized_symbol))
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
        if symbol != self._context.instrument.symbol:
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

    def amend_limit(self, request: PaperLimitAmendRequest) -> PaperLimitMutationResult:
        symbol = request.symbol.strip().upper()
        existing = self.store.get_paper_limit(request.order_id)
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


def _fingerprint(*values: str) -> str:
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()
