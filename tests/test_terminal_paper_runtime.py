import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from terminal.api.models import (
    ClientActionId,
    CloseAllCommandRequest,
    CommandResult,
    CommandResultStatus,
    FullCloseCommandRequest,
    LimitCommandRequest,
    MarketCommandRequest,
    PaperStopMutationRequest,
    VolumeRequest,
    VolumeUnit,
    PaperLimitCancelRequest,
    PaperLimitAmendRequest,
    TimeInForce,
)
from terminal.domain.models import (
    Category, ExecutionId, OrderId, OrderSide, PositionKey, PositionSide, Price, Quantity, Symbol,
)
from terminal.domain.models import TradingAccountId
from terminal.application.trading_accounts import (
    TradingAccount,
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import (
    PaperRuntime, RobotPaperActionExecutor, _robot_protection_crossing_leg,
)
from terminal.persistence.sqlite_store import DuplicateIdentity


class StaticBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=int(__import__("time").time() * 1000),
            available_depth=1,
        )


class ToggleBookProvider(StaticBookProvider):
    unavailable_symbols: set[str]
    stale_symbols: set[str]

    def __init__(self) -> None:
        self.unavailable_symbols = set()
        self.stale_symbols = set()

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        if symbol.value in self.unavailable_symbols:
            return None
        book = super().get_book(symbol)
        if symbol.value in self.stale_symbols:
            return replace(book, received_at_ms=0)
        return book


class MutableBookProvider:
    """Independently controls the execution-time book a dispatch reads
    (self.book_provider.get_book(symbol)) from whatever trigger book a test
    passes into evaluate_robot_protection_crossing -- mirrors the CR's
    trigger-evidence-vs-execution-evidence distinction (section 9)."""

    def __init__(self, symbol: str, book: NormalizedOrderBook) -> None:
        self._books: dict[str, NormalizedOrderBook] = {symbol: book}

    def set_book(self, symbol: str, book: NormalizedOrderBook) -> None:
        self._books[symbol] = book

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        return self._books.get(symbol.value)


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )


def _runtime(path: Path) -> PaperRuntime:
    primary = _instrument()
    return PaperRuntime(
        path,
        book_provider=StaticBookProvider(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
    )


def _runtime_with_provider(path: Path, provider) -> PaperRuntime:
    primary = _instrument()
    return PaperRuntime(
        path,
        book_provider=provider,
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
    )


def test_paper_runtime_rejects_non_paper_active_account() -> None:
    account = TradingAccount(
        TradingAccountId("other"), "Other Paper", TradingAccountProvider.PAPER,
        TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
    )
    manager = TradingAccountManager((account,), active_account_id=account.id)

    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "paper.sqlite3"
        with pytest.raises(RuntimeError, match="authoritative paper account"):
            PaperRuntime(
                database_path,
                book_provider=StaticBookProvider(),
                instrument_snapshot=_instrument(),
                account_manager=manager,
            )
        assert not database_path.exists()


def test_robot_paper_execution_is_independent_of_ui_selected_account():
    """CR: Robot v0.1 PAPER execution decoupling.

    Reproduces the reported failure (Robot orders raising
    live_mutations_disabled once the Workspace UI selects a non-PAPER
    account) and proves the fix: the UI-facing path stays fenced exactly as
    before, while Robot's own execution port (RobotPaperActionExecutor +
    PaperRuntime.robot_match_symbol) is unaffected by UI account selection.
    """

    paper_account = TradingAccount(
        TradingAccountId("paper"), "Paper / Virtual", TradingAccountProvider.PAPER,
        TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
    )
    live_account = TradingAccount(
        TradingAccountId("bybit-1"), "Live Mainnet", TradingAccountProvider.BYBIT,
        TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
    )
    manager = TradingAccountManager(
        (paper_account, live_account), active_account_id=paper_account.id,
    )

    with tempfile.TemporaryDirectory() as temp:
        primary = _instrument()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=StaticBookProvider(),
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(primary, symbol=symbol),
            account_manager=manager,
        )
        # This test drives RobotPaperActionExecutor synchronously on the test
        # thread itself (proving UI-account independence, not the separate
        # cross-thread dispatch fix -- see the production-topology test
        # below), so a same-thread stand-in dispatcher is correct here.
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        try:
            # Operator switches the Workspace UI to a live Bybit account.
            manager.activate(live_account.id)

            with pytest.raises(RuntimeError, match="live_mutations_disabled"):
                runtime.create_limit(LimitCommandRequest(
                    ClientActionId("ui-limit"), "BTCUSDT", OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                    Decimal("64250.5"), Decimal("64250.5"), TimeInForce.GTC,
                ))
            assert runtime.process_orderbook_update("BTCUSDT:1") == 0

            executor = RobotPaperActionExecutor(runtime)
            submitted = executor.create_limit(LimitCommandRequest(
                ClientActionId("robot-limit"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64250.5"), Decimal("64250.5"), TimeInForce.GTC,
            ))
            assert submitted.status is CommandResultStatus.COMPLETED

            applied = runtime.robot_match_symbol("BTCUSDT")
            assert applied == 1

            manager.activate(paper_account.id)
            state = runtime.paper_state("BTCUSDT")
            assert state["position_side"] == "Long"
            assert Decimal(state["position_quantity"]) > 0
        finally:
            runtime.close()


def _crossing_book(symbol: str, *, bid: str, ask: str) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        symbol=Symbol(symbol),
        bids=(PriceLevel(Price(Decimal(bid)), Quantity(Decimal("1"))),),
        asks=(PriceLevel(Price(Decimal(ask)), Quantity(Decimal("1"))),),
        health=BookHealth.READY,
        # Fresh real time -- D2.3 dispatch may feed this same book straight
        # into PaperMarketExecutor.execute(), which fails closed on a stale
        # (max_book_age_ms) book; a fixed historical timestamp would make
        # every real close attempt in these tests spuriously stale.
        received_at_ms=int(__import__("time").time() * 1000),
        available_depth=1,
    )


def _open_robot_position_with_confirmed_protection(
    runtime: PaperRuntime, *, symbol: str, entry_price: Decimal,
    stop_price: Decimal, take_price: Decimal, trade_id: str, candidate_id: str,
) -> None:
    """Real Robot LIMIT fill + confirmed STOP/TAKE, then the D2.1 robot_trades
    row a production RobotBreakoutMonitor tick would create in the same tick
    -- everything evaluate_robot_protection_crossing() needs to cover."""
    runtime._robot_command_dispatcher = lambda operation: operation(runtime)
    executor = RobotPaperActionExecutor(runtime)
    submitted = executor.create_limit(LimitCommandRequest(
        ClientActionId(f"{trade_id}-limit"), symbol, OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal("321")),
        entry_price, entry_price, TimeInForce.GTC,
    ))
    assert submitted.status is CommandResultStatus.COMPLETED
    assert runtime.robot_match_symbol(symbol) == 1

    executor.create_stop(PaperStopMutationRequest(
        ClientActionId(f"{trade_id}-stop"), symbol, stop_price,
    ))
    executor.create_take(PaperStopMutationRequest(
        ClientActionId(f"{trade_id}-take"), symbol, take_price,
    ))

    runtime.store.create_robot_candidate(
        candidate_id=candidate_id, trading_account_id=TradingAccountId("paper"),
        symbol=Symbol(symbol), status="APPROVED",
        signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge"},
        approved_at_ms=1000, updated_at_ms=1000,
    )
    # Owner-frozen D2.3 ownership attestation: exactly what the real
    # RobotBreakoutMonitor._finalize_trade() now reads -- the authoritative
    # position projection's own quantity/version right after entry finalized.
    entry_projection = runtime.store.get_position_projection(
        PositionKey(TradingAccountId("paper"), Category.LINEAR, Symbol(symbol), 0)
    )
    runtime.store.create_robot_trade(
        trade_id=trade_id, trading_account_id=TradingAccountId("paper"),
        candidate_id=candidate_id, symbol=Symbol(symbol), direction="LONG",
        pattern="Falling Wedge", source_timeframe="1", signal_time_ms=900,
        entry_time_ms=1500, entry_path="LIMIT", actual_wv=Decimal("0.8"),
        average_entry=entry_price, stop_price=stop_price, take_price=take_price,
        entry_quantity=entry_projection.quantity.value,
        entry_position_version=entry_projection.version,
        created_at_ms=1500,
    )


def test_robot_protection_crossing_leg_preserves_long_short_and_stop_precedence():
    assert _robot_protection_crossing_leg(
        PositionSide.LONG, Decimal("98"), Decimal("104"), Decimal("97.9"),
    ) == "STOP"
    assert _robot_protection_crossing_leg(
        PositionSide.LONG, Decimal("98"), Decimal("104"), Decimal("104.1"),
    ) == "TAKE"
    assert _robot_protection_crossing_leg(
        PositionSide.LONG, Decimal("98"), Decimal("104"), Decimal("100"),
    ) is None
    assert _robot_protection_crossing_leg(
        PositionSide.SHORT, Decimal("104"), Decimal("98"), Decimal("104.1"),
    ) == "STOP"
    assert _robot_protection_crossing_leg(
        PositionSide.SHORT, Decimal("104"), Decimal("98"), Decimal("97.9"),
    ) == "TAKE"
    # Invalid/crossed geometry (STOP above TAKE for LONG) can still qualify
    # both legs on one valid observation -- STOP must win, not be repaired.
    assert _robot_protection_crossing_leg(
        PositionSide.LONG, Decimal("100"), Decimal("90"), Decimal("95"),
    ) == "STOP"
    assert _robot_protection_crossing_leg(
        PositionSide.LONG, None, Decimal("104"), Decimal("50"),
    ) is None


def test_evaluate_robot_protection_crossing_latches_first_leg_and_survives_retreat_and_duplicates():
    """D2.1 latch survives retreat/duplicate observations; D2.3 dispatch is
    attempted on every observation once latched (never re-evaluating the
    crossing predicate) but fails closed while no execution-time book is
    available, without losing or duplicating the obligation -- only a later
    valid book actually resolves it (CR sections 9/11, T08/T09)."""
    with tempfile.TemporaryDirectory() as temp:
        # No execution-time book yet: any dispatch attempt must fail closed
        # (RuntimeError from PaperMarketExecutor) rather than erase the latch.
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-crossing-1", candidate_id="candidate-crossing-1",
            )
            executions_after_entry = len(runtime.store.load_executions())
            provider.set_book("BTCUSDT", None)

            latched = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", _crossing_book("BTCUSDT", bid="63990", ask="63995"),
                event_id="evt-1", received_at_ms=2000,
            )
            assert latched is not None
            assert latched.winning_leg == "STOP"
            assert latched.trade_id == "trade-crossing-1"
            assert latched.status == "DISPATCHING"

            # Retreat: this observation crosses neither leg, but the
            # obligation is already latched -- dispatch is attempted
            # regardless (using whatever the current book is), and it must
            # survive the still-unavailable execution book unchanged.
            retreated = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", _crossing_book("BTCUSDT", bid="64300", ask="64305"),
                event_id="evt-2", received_at_ms=2100,
            )
            assert retreated == latched
            assert runtime.store.get_paper_protection_obligation(
                latched.obligation_id
            ) == latched

            # Duplicate crossing evidence must not create a second obligation.
            duplicate = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", _crossing_book("BTCUSDT", bid="63980", ask="63985"),
                event_id="evt-3", received_at_ms=2200,
            )
            assert duplicate == latched
            assert len(runtime.store.load_executions()) == executions_after_entry

            # Only once a valid execution-time book actually appears does the
            # committed obligation resolve -- using that current book, not
            # any of the earlier (trigger-only) observations above.
            provider.set_book("BTCUSDT", _crossing_book("BTCUSDT", bid="63970", ask="63975"))
            resolved = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", _crossing_book("BTCUSDT", bid="63960", ask="63965"),
                event_id="evt-4", received_at_ms=2300,
            )
            assert resolved.status == "RESOLVED"
            trade = runtime.store.get_robot_trade("trade-crossing-1")
            assert trade.exit_time_ms is not None
            assert trade.exit_price == Decimal("63970")
        finally:
            runtime.close()


def test_evaluate_robot_protection_crossing_returns_none_without_confirmed_protection():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            runtime._robot_command_dispatcher = lambda operation: operation(runtime)
            executor = RobotPaperActionExecutor(runtime)
            submitted = executor.create_limit(LimitCommandRequest(
                ClientActionId("no-protection-limit"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64250.5"), Decimal("64250.5"), TimeInForce.GTC,
            ))
            assert submitted.status is CommandResultStatus.COMPLETED
            assert runtime.robot_match_symbol("BTCUSDT") == 1

            runtime.store.create_robot_candidate(
                candidate_id="candidate-no-protection", trading_account_id=TradingAccountId("paper"),
                symbol=Symbol("BTCUSDT"), status="APPROVED",
                signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
                approved_at_ms=1000, updated_at_ms=1000,
            )
            runtime.store.create_robot_trade(
                trade_id="trade-no-protection", trading_account_id=TradingAccountId("paper"),
                candidate_id="candidate-no-protection", symbol=Symbol("BTCUSDT"),
                direction="LONG", pattern="Falling Wedge", source_timeframe="1",
                signal_time_ms=900, entry_time_ms=1500, entry_path="LIMIT",
                actual_wv=Decimal("0.8"), average_entry=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                entry_quantity=Decimal("0.004"), entry_position_version=1, created_at_ms=1500,
            )

            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", _crossing_book("BTCUSDT", bid="63000", ask="63005"),
                event_id="evt-1", received_at_ms=2000,
            )
            assert result is None
            assert runtime.store.load_unresolved_paper_protection_obligations(
                TradingAccountId("paper")
            ) == ()
        finally:
            runtime.close()


def test_evaluate_robot_protection_crossing_fails_closed_on_ambiguous_open_trades():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-ambiguous-1", candidate_id="candidate-ambiguous-1",
            )
            runtime.store.create_robot_candidate(
                candidate_id="candidate-ambiguous-2", trading_account_id=TradingAccountId("paper"),
                symbol=Symbol("BTCUSDT"), status="APPROVED",
                signal_snapshot={"symbol": "BTCUSDT", "pattern": "second"},
                approved_at_ms=1000, updated_at_ms=1000,
            )
            runtime.store.create_robot_trade(
                trade_id="trade-ambiguous-2", trading_account_id=TradingAccountId("paper"),
                candidate_id="candidate-ambiguous-2", symbol=Symbol("BTCUSDT"),
                direction="LONG", pattern="second", source_timeframe="1",
                signal_time_ms=900, entry_time_ms=1500, entry_path="LIMIT",
                actual_wv=Decimal("0.2"), average_entry=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                entry_quantity=Decimal("0.002"), entry_position_version=1, created_at_ms=1500,
            )

            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", _crossing_book("BTCUSDT", bid="63000", ask="63005"),
                event_id="evt-1", received_at_ms=2000,
            )
            assert result is None
        finally:
            runtime.close()


def test_robot_protection_coverage_symbols_reflects_open_robot_candidates_only():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            assert runtime.robot_protection_coverage_symbols() == ()

            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-coverage-1", candidate_id="candidate-coverage-1",
            )
            assert runtime.robot_protection_coverage_symbols() == ("BTCUSDT",)

            runtime.store.close_robot_trade(
                "trade-coverage-1", exit_time_ms=3000, exit_price=Decimal("64600"),
                exit_reason="TAKE", realized_pnl_usdt=Decimal("1"), realized_pnl_pct=Decimal("0.5"),
                fees_costs_usdt=Decimal("0.1"), updated_at_ms=3000,
            )
            assert runtime.robot_protection_coverage_symbols() == ()
        finally:
            runtime.close()


def test_robot_protection_coverage_symbols_unions_open_trades_and_unresolved_obligations():
    """D2.2 review fix: a persisted TRIGGERED/DISPATCHING obligation must keep
    market-data coverage even once candidate/trade projection state alone
    (status == OPEN) is no longer sufficient to prove it -- e.g. after some
    later process closes the trade while the durable obligation is still
    unresolved (no dispatch/finalization exists in this slice)."""
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            account = TradingAccountId("paper")

            # BTCUSDT: currently OPEN Robot trade, no obligation latched yet.
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-open-only", candidate_id="candidate-open-only",
            )

            # ETHUSDT: trade already closed, but its obligation is not
            # resolved -- coverage responsibility must still follow it.
            runtime.store.create_robot_candidate(
                candidate_id="candidate-unresolved-only", trading_account_id=account,
                symbol=Symbol("ETHUSDT"), status="APPROVED",
                signal_snapshot={"symbol": "ETHUSDT", "pattern": "Falling Wedge"},
                approved_at_ms=1000, updated_at_ms=1000,
            )
            runtime.store.create_robot_trade(
                trade_id="trade-unresolved-only", trading_account_id=account,
                candidate_id="candidate-unresolved-only", symbol=Symbol("ETHUSDT"),
                direction="LONG", pattern="Falling Wedge", source_timeframe="1",
                signal_time_ms=900, entry_time_ms=1500, entry_path="LIMIT",
                actual_wv=Decimal("0.8"), average_entry=Decimal("100"),
                stop_price=Decimal("98"), take_price=Decimal("104"),
                entry_quantity=Decimal("1"), entry_position_version=1, created_at_ms=1500,
            )
            runtime.store.latch_paper_protection_obligation(
                trade_id="trade-unresolved-only", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("98"), observed_exit_price=Decimal("97.9"),
                observed_quantity=Decimal("1"), market_event_id="evt-1",
                source_received_at_ms=2000, latched_at_ms=2000,
            )
            runtime.store.close_robot_trade(
                "trade-unresolved-only", exit_time_ms=3000, exit_price=Decimal("98"),
                exit_reason="STOP", realized_pnl_usdt=Decimal("-2"),
                realized_pnl_pct=Decimal("-2"), fees_costs_usdt=Decimal("0.1"),
                updated_at_ms=3000,
            )

            assert runtime.robot_protection_coverage_symbols() == ("BTCUSDT", "ETHUSDT")
        finally:
            runtime.close()


def _entry_book() -> NormalizedOrderBook:
    return _crossing_book("BTCUSDT", bid="64249.5", ask="64250.5")


def test_dispatch_resolves_stop_close_and_finalizes_robot_trade_with_frozen_pnl_pct():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-stop-1", candidate_id="candidate-stop-1",
            )
            position_key = PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            )
            entry_quantity = runtime.store.get_position_projection(position_key).quantity.value

            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)

            obligation = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-stop", received_at_ms=5000,
            )

            assert obligation is not None
            assert obligation.status == "RESOLVED"
            assert obligation.winning_leg == "STOP"
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"

            trade = runtime.store.get_robot_trade("trade-stop-1")
            assert trade.exit_time_ms is not None
            assert trade.exit_reason == "STOP"
            assert trade.exit_price == Decimal("63990")
            expected_pnl = entry_quantity * (Decimal("63990") - Decimal("64250.5"))
            assert trade.realized_pnl_usdt == expected_pnl
            expected_notional = entry_quantity * Decimal("64250.5")
            expected_pct = (
                (expected_pnl - trade.fees_costs_usdt) / expected_notional * 100
            )
            assert trade.realized_pnl_pct == expected_pct

            candidates = runtime.store.load_robot_candidates(TradingAccountId("paper"))
            candidate = next(c for c in candidates if c.candidate_id == "candidate-stop-1")
            assert candidate.status == "CLOSED"

            executions_after_first_resolution = len(runtime.store.load_executions())
            assert any(
                execution.order_id == obligation.order_id
                for execution in runtime.store.load_executions()
            )

            # A duplicate/late quote after resolution must be a safe no-op:
            # no re-execution, no obligation/trade mutation, no crash.
            repeat = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-stop-dup", received_at_ms=5100,
            )
            assert repeat is None
            assert len(runtime.store.load_executions()) == executions_after_first_resolution
            assert runtime.store.get_robot_trade("trade-stop-1") == trade
        finally:
            runtime.close()


def test_dispatch_resolves_take_close_and_finalizes_robot_trade():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-take-1", candidate_id="candidate-take-1",
            )
            close_book = _crossing_book("BTCUSDT", bid="64650", ask="64655")
            provider.set_book("BTCUSDT", close_book)

            obligation = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-take", received_at_ms=5000,
            )

            assert obligation is not None
            assert obligation.status == "RESOLVED"
            assert obligation.winning_leg == "TAKE"
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"

            trade = runtime.store.get_robot_trade("trade-take-1")
            assert trade.exit_reason == "TAKE"
            assert trade.exit_price == Decimal("64650")
            assert trade.realized_pnl_usdt > 0
        finally:
            runtime.close()


def test_dispatch_uses_current_position_quantity_not_stale_observed_quantity():
    """CR section 7/9: shared position evidence remains current-quantity
    authority. An obligation's own observed_quantity (recorded at latch time)
    must never be used to size the close -- only the position's actual
    current quantity at dispatch time."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-qty-1", candidate_id="candidate-qty-1",
            )
            position_key = PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            )
            entry_quantity = runtime.store.get_position_projection(position_key).quantity.value

            # Manually latch with a deliberately wrong observed_quantity --
            # dispatch must ignore it and close the real current quantity.
            runtime.store.latch_paper_protection_obligation(
                trade_id="trade-qty-1", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("64000"), observed_exit_price=Decimal("63990"),
                observed_quantity=Decimal("999"), market_event_id="evt-qty-latch",
                source_received_at_ms=4000, latched_at_ms=4000,
            )

            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)
            obligation = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-qty-dispatch", received_at_ms=4100,
            )

            assert obligation.status == "RESOLVED"
            executions = runtime.store.load_executions()
            closing_execution = next(e for e in executions if e.order_id == obligation.order_id)
            assert closing_execution.quantity.value == entry_quantity
        finally:
            runtime.close()


def test_dispatch_resumes_from_triggered_after_restart():
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "paper.sqlite3"
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(db_path, provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-restart-triggered", candidate_id="candidate-restart-triggered",
            )
            # Only latch (D2.1) -- simulate a crash before any dispatch attempt.
            latched, _ = runtime.store.latch_paper_protection_obligation(
                trade_id="trade-restart-triggered", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("64000"), observed_exit_price=Decimal("63990"),
                observed_quantity=Decimal("1"), market_event_id="evt-restart-latch",
                source_received_at_ms=4000, latched_at_ms=4000,
            )
            assert latched.status == "TRIGGERED"
        finally:
            runtime.close()

        resumed_provider = MutableBookProvider(
            "BTCUSDT", _crossing_book("BTCUSDT", bid="63990", ask="63995"),
        )
        resumed = _runtime_with_provider(db_path, resumed_provider)
        try:
            obligation = resumed.evaluate_robot_protection_crossing(
                "BTCUSDT", resumed_provider.get_book(Symbol("BTCUSDT")),
                event_id="evt-restart-resume", received_at_ms=6000,
            )
            assert obligation is not None
            assert obligation.status == "RESOLVED"
            trade = resumed.store.get_robot_trade("trade-restart-triggered")
            assert trade.exit_time_ms is not None
            assert trade.exit_reason == "STOP"
        finally:
            resumed.close()


def test_dispatch_resumes_from_dispatching_before_execution_after_restart():
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "paper.sqlite3"
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(db_path, provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-restart-dispatching", candidate_id="candidate-restart-dispatching",
            )
            latched, _ = runtime.store.latch_paper_protection_obligation(
                trade_id="trade-restart-dispatching", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("64000"), observed_exit_price=Decimal("63990"),
                observed_quantity=Decimal("1"), market_event_id="evt-restart-latch-2",
                source_received_at_ms=4000, latched_at_ms=4000,
            )
            # Simulate a crash right after the claim, before execute() ran.
            claimed = runtime.store.transition_paper_protection_obligation(
                latched.obligation_id, expected_status="TRIGGERED", next_status="DISPATCHING",
                expected_version=latched.version, updated_at_ms=4001,
            )
            assert claimed.status == "DISPATCHING"
            executions_before_execute = len(runtime.store.load_executions())
        finally:
            runtime.close()

        resumed_provider = MutableBookProvider(
            "BTCUSDT", _crossing_book("BTCUSDT", bid="63990", ask="63995"),
        )
        resumed = _runtime_with_provider(db_path, resumed_provider)
        try:
            assert len(resumed.store.load_executions()) == executions_before_execute
            obligation = resumed.evaluate_robot_protection_crossing(
                "BTCUSDT", resumed_provider.get_book(Symbol("BTCUSDT")),
                event_id="evt-restart-resume-2", received_at_ms=6000,
            )
            assert obligation is not None
            assert obligation.status == "RESOLVED"
            trade = resumed.store.get_robot_trade("trade-restart-dispatching")
            assert trade.exit_time_ms is not None
        finally:
            resumed.close()


def test_dispatch_resumes_from_dispatching_after_execution_before_finalization_after_restart():
    with tempfile.TemporaryDirectory() as temp:
        db_path = Path(temp) / "paper.sqlite3"
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(db_path, provider)
        close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-restart-executed", candidate_id="candidate-restart-executed",
            )
            position_key = PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            )
            quantity = runtime.store.get_position_projection(position_key).quantity.value
            latched, _ = runtime.store.latch_paper_protection_obligation(
                trade_id="trade-restart-executed", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("64000"), observed_exit_price=Decimal("63990"),
                observed_quantity=Decimal("1"), market_event_id="evt-restart-latch-3",
                source_received_at_ms=4000, latched_at_ms=4000,
            )
            claimed = runtime.store.transition_paper_protection_obligation(
                latched.obligation_id, expected_status="TRIGGERED", next_status="DISPATCHING",
                expected_version=latched.version, updated_at_ms=4001,
            )
            provider.set_book("BTCUSDT", close_book)
            # Simulate the close having actually executed before the crash --
            # using the obligation's own stable D2.1 order/exec identity, exactly
            # as _dispatch_paper_protection_obligation would.
            runtime._market_executor.execute(
                trading_account_id=TradingAccountId("paper"),
                symbol=Symbol("BTCUSDT"),
                side=OrderSide.SELL,
                quantity=Quantity(quantity),
                order_link_id=claimed.obligation_id,
                order_id=claimed.order_id,
                exec_id=claimed.exec_id,
            )
            executions_before_restart = len(runtime.store.load_executions())
            # Neither the trade nor the candidate may be finalized yet -- proven
            # execution evidence alone is not proven finalization.
            assert runtime.store.get_robot_trade("trade-restart-executed").exit_time_ms is None
            candidates = runtime.store.load_robot_candidates(TradingAccountId("paper"))
            assert next(
                c for c in candidates if c.candidate_id == "candidate-restart-executed"
            ).status == "OPEN"
        finally:
            runtime.close()

        resumed_provider = MutableBookProvider("BTCUSDT", close_book)
        resumed = _runtime_with_provider(db_path, resumed_provider)
        try:
            obligation = resumed.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-restart-resume-3", received_at_ms=6000,
            )
            assert obligation is not None
            assert obligation.status == "RESOLVED"
            assert len(resumed.store.load_executions()) == executions_before_restart

            trade = resumed.store.get_robot_trade("trade-restart-executed")
            assert trade.exit_time_ms is not None
            assert trade.exit_reason == "STOP"
            candidates = resumed.store.load_robot_candidates(TradingAccountId("paper"))
            assert next(
                c for c in candidates if c.candidate_id == "candidate-restart-executed"
            ).status == "CLOSED"
        finally:
            resumed.close()


def test_dispatch_fails_closed_when_manual_close_wins_race_before_our_exec():
    """Manual/replacement ambiguity must fail closed (CR failure-mode table):
    if the position is flattened by something other than this obligation's
    own stable exec before dispatch runs, dispatch must not attribute that
    fill to itself, must not call close_robot_trade(), and must leave the
    obligation for reconciliation instead of guessing."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-manual-race", candidate_id="candidate-manual-race",
            )
            latched, _ = runtime.store.latch_paper_protection_obligation(
                trade_id="trade-manual-race", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("64000"), observed_exit_price=Decimal("63990"),
                observed_quantity=Decimal("1"), market_event_id="evt-manual-latch",
                source_received_at_ms=4000, latched_at_ms=4000,
            )

            # A manual full_close wins the race and flattens the position
            # through a different (non-obligation) exec before our dispatch runs.
            manual_close = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("manual-race-close"), "BTCUSDT")
            )
            assert manual_close.status is CommandResultStatus.COMPLETED
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"

            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)
            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-manual-dispatch", received_at_ms=4100,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert result.obligation_id == latched.obligation_id

            trade = runtime.store.get_robot_trade("trade-manual-race")
            assert trade.exit_time_ms is None
            candidates = runtime.store.load_robot_candidates(TradingAccountId("paper"))
            assert next(
                c for c in candidates if c.candidate_id == "candidate-manual-race"
            ).status == "OPEN"
        finally:
            runtime.close()


def test_dispatch_fails_closed_when_entry_quantity_attestation_is_missing():
    """D2.3 review-fix: a legacy (pre-v18) trade with NULL entry_quantity
    must fail closed rather than fall back to guessing the aggregate."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-missing-qty", candidate_id="candidate-missing-qty",
            )
            runtime.store._connection.execute(
                "UPDATE robot_trades SET entry_quantity=NULL WHERE trade_id=?",
                ("trade-missing-qty",),
            )
            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)

            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-missing-qty", received_at_ms=5000,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert runtime.store.get_robot_trade("trade-missing-qty").exit_time_ms is None
        finally:
            runtime.close()


def test_dispatch_fails_closed_when_entry_position_version_attestation_is_missing():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-missing-version", candidate_id="candidate-missing-version",
            )
            runtime.store._connection.execute(
                "UPDATE robot_trades SET entry_position_version=NULL WHERE trade_id=?",
                ("trade-missing-version",),
            )
            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)

            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-missing-version", received_at_ms=5000,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert runtime.store.get_robot_trade("trade-missing-version").exit_time_ms is None
        finally:
            runtime.close()


def test_dispatch_fails_closed_on_entry_quantity_mismatch():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-qty-mismatch", candidate_id="candidate-qty-mismatch",
            )
            trade = runtime.store.get_robot_trade("trade-qty-mismatch")
            corrupted_quantity = trade.entry_quantity + Decimal("1")
            runtime.store._connection.execute(
                "UPDATE robot_trades SET entry_quantity=? WHERE trade_id=?",
                (str(corrupted_quantity), "trade-qty-mismatch"),
            )
            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)

            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-qty-mismatch", received_at_ms=5000,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert runtime.store.get_robot_trade("trade-qty-mismatch").exit_time_ms is None
        finally:
            runtime.close()


def test_dispatch_fails_closed_on_entry_position_version_mismatch():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-version-mismatch", candidate_id="candidate-version-mismatch",
            )
            trade = runtime.store.get_robot_trade("trade-version-mismatch")
            runtime.store._connection.execute(
                "UPDATE robot_trades SET entry_position_version=? WHERE trade_id=?",
                (trade.entry_position_version + 1, "trade-version-mismatch"),
            )
            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)

            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-version-mismatch", received_at_ms=5000,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert runtime.store.get_robot_trade("trade-version-mismatch").exit_time_ms is None
        finally:
            runtime.close()


def test_dispatch_fails_closed_after_manual_add_to_robot_position():
    """Owner counterexample: Robot 100 + manual +40 -> aggregate 140. Proves
    the fail-closed path end to end through evaluate_robot_protection_crossing,
    not only at the raw attestation comparison."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-manual-add", candidate_id="candidate-manual-add",
            )
            # Manual LONG add on the same shared aggregate position.
            runtime._market_executor.execute(
                trading_account_id=TradingAccountId("paper"), symbol=Symbol("BTCUSDT"),
                side=OrderSide.BUY, quantity=Quantity(Decimal("0.001")),
                order_link_id="manual-add-1", order_id=OrderId("manual-add-order-1"),
                exec_id=ExecutionId("manual-add-exec-1"),
            )

            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)
            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-manual-add", received_at_ms=5000,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert runtime.store.get_robot_trade("trade-manual-add").exit_time_ms is None
        finally:
            runtime.close()


def test_dispatch_fails_closed_after_manual_add_then_reduce_nets_back_to_original_quantity():
    """Owner counterexample: Robot 100, manual +40, manual -40 -> aggregate
    back to 100. A quantity-only check would wrongly pass; the
    entry_position_version watermark (bumped by both manual fills) must
    still catch it."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-manual-round-trip", candidate_id="candidate-manual-round-trip",
            )
            trade = runtime.store.get_robot_trade("trade-manual-round-trip")

            runtime._market_executor.execute(
                trading_account_id=TradingAccountId("paper"), symbol=Symbol("BTCUSDT"),
                side=OrderSide.BUY, quantity=Quantity(Decimal("0.001")),
                order_link_id="manual-round-trip-add",
                order_id=OrderId("manual-round-trip-add-order"),
                exec_id=ExecutionId("manual-round-trip-add-exec"),
            )
            runtime._market_executor.execute(
                trading_account_id=TradingAccountId("paper"), symbol=Symbol("BTCUSDT"),
                side=OrderSide.SELL, quantity=Quantity(Decimal("0.001")),
                order_link_id="manual-round-trip-reduce",
                order_id=OrderId("manual-round-trip-reduce-order"),
                exec_id=ExecutionId("manual-round-trip-reduce-exec"),
            )

            position_key = PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            )
            position_after = runtime.store.get_position_projection(position_key)
            # Quantity really did net back to exactly the Robot's own entry --
            # only the version watermark can still see the round trip.
            assert position_after.quantity.value == trade.entry_quantity
            assert position_after.version != trade.entry_position_version

            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)
            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-manual-round-trip", received_at_ms=5000,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert runtime.store.get_robot_trade("trade-manual-round-trip").exit_time_ms is None
        finally:
            runtime.close()


def test_dispatch_fails_closed_on_replacement_lifecycle_with_same_quantity():
    """Owner counterexample: a replacement lifecycle could end up with the
    same side/quantity as the original Robot entry. The version watermark
    (bumped by the flatten and the new entry) must still distinguish it from
    the untouched original lifecycle even though the quantity coincides."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-replacement", candidate_id="candidate-replacement",
            )
            trade = runtime.store.get_robot_trade("trade-replacement")
            original_quantity = trade.entry_quantity

            latched, _ = runtime.store.latch_paper_protection_obligation(
                trade_id="trade-replacement", protection_version=1, winning_leg="STOP",
                trigger_price=Decimal("64000"), observed_exit_price=Decimal("63990"),
                observed_quantity=Decimal("1"), market_event_id="evt-replacement-latch",
                source_received_at_ms=4000, latched_at_ms=4000,
            )

            # The original lifecycle is flattened by something other than our
            # own dispatch (e.g. manual full_close, which never calls
            # close_robot_trade()), then a replacement position opens on the
            # same symbol with the SAME quantity.
            manual_close = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("replacement-close"), "BTCUSDT")
            )
            assert manual_close.status is CommandResultStatus.COMPLETED
            runtime._market_executor.execute(
                trading_account_id=TradingAccountId("paper"), symbol=Symbol("BTCUSDT"),
                side=OrderSide.BUY, quantity=Quantity(original_quantity),
                order_link_id="replacement-entry", order_id=OrderId("replacement-entry-order"),
                exec_id=ExecutionId("replacement-entry-exec"),
            )
            position_key = PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            )
            replacement_position = runtime.store.get_position_projection(position_key)
            # The coincidence the owner described: quantity/side match again.
            assert replacement_position.quantity.value == original_quantity
            assert replacement_position.side is PositionSide.LONG
            assert replacement_position.version != trade.entry_position_version

            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)
            result = runtime.evaluate_robot_protection_crossing(
                "BTCUSDT", close_book, event_id="evt-replacement-dispatch", received_at_ms=4200,
            )

            assert result is not None
            assert result.status == "TRIGGERED"
            assert result.obligation_id == latched.obligation_id
            # The replacement position must remain untouched -- never closed
            # under the old obligation's identity.
            assert (
                runtime.store.get_position_projection(position_key).quantity.value
                == original_quantity
            )
            assert runtime.store.get_robot_trade("trade-replacement").exit_time_ms is None
        finally:
            runtime.close()


def test_cancel_limit_succeeds_for_a_symbol_other_than_the_startup_instrument():
    """cancel_limit() used to reject any symbol other than the runtime's fixed
    startup instrument (self._context.instrument.symbol) even though the
    order's own symbol was already validated correctly two lines below --
    a redundant, overly-narrow check that would have blocked Robot's
    partial-fill cancel-remainder step on any non-startup symbol."""

    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            created = runtime.create_limit(LimitCommandRequest(
                ClientActionId("eth-create"), "ETHUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64250.5"), Decimal("64250.5"), TimeInForce.GTC,
            ))
            assert created.status is CommandResultStatus.COMPLETED

            cancelled = runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("eth-cancel"), "ETHUSDT", created.order_id,
            ))
            assert cancelled.status is CommandResultStatus.COMPLETED
        finally:
            runtime.close()


def test_composed_paper_runtime_market_buy_completes():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            result = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-buy-1"),
                    "BTCUSDT",
                    OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                    Decimal("64250"),
                    "Percent",
                    Decimal("0.5"),
                )
            )

            assert result.status is CommandResultStatus.COMPLETED
            assert result.command_id is not None
            assert result.reconciliation_required is False
            assert len(runtime.store.load_executions()) == 1
        finally:
            runtime.close()


def test_full_close_uses_authoritative_remaining_quantity_and_flat_repeat_is_noop():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            opened = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-open-long"), "BTCUSDT", OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                )
            )
            assert opened.status is CommandResultStatus.COMPLETED
            before_close = runtime.paper_state("BTCUSDT")
            assert before_close["account_id"] == "paper"
            assert before_close["position_side"] == "Long"
            assert before_close["average_entry"] is not None

            closed = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-long"), "BTCUSDT")
            )
            assert closed.status is CommandResultStatus.COMPLETED
            state = runtime.paper_state("BTCUSDT")
            assert state["position_side"] == "Flat"
            assert state["average_entry"] is None
            assert state["position_quantity"] == "0"
            assert state["engaged_notional_usdt"] == "0"
            assert state["engaged_wv"] == "0.0"
            execution_count = len(runtime.store.load_executions())

            repeated = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-flat"), "BTCUSDT")
            )
            assert repeated.status is CommandResultStatus.COMPLETED
            assert repeated.reason_code == "already_flat"
            assert len(runtime.store.load_executions()) == execution_count
        finally:
            runtime.close()


def test_full_close_closes_short_without_flipping_long():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            opened = runtime.api.market(
                MarketCommandRequest(
                    ClientActionId("runtime-open-short"), "BTCUSDT", OrderSide.SELL,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                )
            )
            assert opened.status is CommandResultStatus.COMPLETED
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Short"
            closed = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("runtime-close-short"), "BTCUSDT")
            )
            assert closed.status is CommandResultStatus.COMPLETED
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
        finally:
            runtime.close()


def test_paper_limit_create_is_durable_idempotent_and_cancel_is_safe():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            request = LimitCommandRequest(
                ClientActionId("limit-buy-1"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64000"), Decimal("64000"), TimeInForce.GTC,
            )
            created = runtime.create_limit(request)
            duplicate = runtime.create_limit(request)
            assert created.status is CommandResultStatus.COMPLETED
            assert duplicate.order_id == created.order_id
            assert duplicate.reason_code == "duplicate_action"
            try:
                runtime.create_limit(LimitCommandRequest(
                    ClientActionId("limit-buy-1"), "BTCUSDT", OrderSide.SELL,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                    Decimal("64000"), Decimal("64000"), TimeInForce.GTC,
                ))
            except DuplicateIdentity:
                pass
            else:
                raise AssertionError("conflicting duplicate client action must fail closed")
            active = runtime.paper_state("BTCUSDT")["active_limit_orders"]
            assert len(active) == 1
            assert active[0]["side"] == "Buy"
            assert active[0]["time_in_force"] == "GTC"

            cancelled = runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("limit-cancel-1"), "BTCUSDT", created.order_id,
            ))
            repeated = runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("limit-cancel-2"), "BTCUSDT", created.order_id,
            ))
            assert cancelled.status is CommandResultStatus.COMPLETED
            assert repeated.status is CommandResultStatus.COMPLETED
            assert repeated.reason_code == "already_absent"
            assert runtime.paper_state("BTCUSDT")["active_limit_orders"] == []
        finally:
            runtime.close()


def test_paper_sell_limit_uses_shared_sizing_and_gtc():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            result = runtime.create_limit(LimitCommandRequest(
                ClientActionId("limit-sell-1"), "BTCUSDT", OrderSide.SELL,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("65000"), Decimal("65000"), TimeInForce.GTC,
            ))
            assert result.status is CommandResultStatus.COMPLETED
            active = runtime.paper_state("BTCUSDT")["active_limit_orders"]
            assert active[0]["side"] == "Sell"
            assert active[0]["quantity"] == "0.004"
            assert active[0]["time_in_force"] == "GTC"
        finally:
            runtime.close()


def test_paper_limit_amend_reprices_in_place_and_is_durable_idempotent():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            created = runtime.create_limit(LimitCommandRequest(
                ClientActionId("limit-amend-create"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("64000"), Decimal("64000"), TimeInForce.GTC,
            ))
            before = runtime.paper_state("BTCUSDT")["active_limit_orders"][0]
            request = PaperLimitAmendRequest(
                ClientActionId("limit-amend-1"), "BTCUSDT", created.order_id,
                Decimal("64100.24"),
            )
            amended = runtime.amend_limit(request)
            duplicate = runtime.amend_limit(request)
            after = runtime.paper_state("BTCUSDT")["active_limit_orders"][0]

            assert amended.reason_code == "amended"
            assert duplicate.reason_code == "duplicate_action"
            assert after["order_id"] == before["order_id"]
            assert after["side"] == before["side"]
            assert after["quantity"] == before["quantity"]
            assert after["time_in_force"] == "GTC"
            assert after["price"] == "64100.0"
            assert len(runtime.store.load_active_paper_limits(
                TradingAccountId("paper"), Symbol("BTCUSDT"),
            )) == 1

            try:
                runtime.amend_limit(PaperLimitAmendRequest(
                    ClientActionId("limit-amend-1"), "BTCUSDT", created.order_id,
                    Decimal("63900"),
                ))
            except DuplicateIdentity:
                pass
            else:
                raise AssertionError("conflicting amend action identity must fail closed")
        finally:
            runtime.close()


def test_paper_limit_amend_missing_or_inactive_fails_closed():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for order_id in ("missing",):
                try:
                    runtime.amend_limit(PaperLimitAmendRequest(
                        ClientActionId("amend-missing"), "BTCUSDT", order_id,
                        Decimal("64100"),
                    ))
                except ValueError:
                    pass
                else:
                    raise AssertionError("missing order amend must fail closed")

            created = runtime.create_limit(LimitCommandRequest(
                ClientActionId("inactive-create"), "BTCUSDT", OrderSide.SELL,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")),
                Decimal("65000"), Decimal("65000"), TimeInForce.GTC,
            ))
            runtime.cancel_limit(PaperLimitCancelRequest(
                ClientActionId("inactive-cancel"), "BTCUSDT", created.order_id,
            ))
            try:
                runtime.amend_limit(PaperLimitAmendRequest(
                    ClientActionId("amend-inactive"), "BTCUSDT", created.order_id,
                    Decimal("65100"),
                ))
            except ValueError:
                pass
            else:
                raise AssertionError("inactive order amend must fail closed")
        finally:
            runtime.close()


def test_account_inventory_is_multi_symbol_and_close_is_symbol_scoped():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for symbol, side, action in (
                ("BTCUSDT", OrderSide.BUY, "inventory-btc"),
                ("ETHUSDT", OrderSide.SELL, "inventory-eth"),
            ):
                result = runtime.api.market(MarketCommandRequest(
                    ClientActionId(action), symbol, side,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                ))
                assert result.status is CommandResultStatus.COMPLETED

            inventory = runtime.open_positions()
            assert inventory.account_id == "paper"
            assert [item.symbol for item in inventory.positions] == ["BTCUSDT", "ETHUSDT"]
            assert [item.position_side for item in inventory.positions] == ["Long", "Short"]

            closed = runtime.api.full_close(FullCloseCommandRequest(
                ClientActionId("inventory-close-btc"), "BTCUSDT",
            ))
            assert closed.status is CommandResultStatus.COMPLETED
            assert [item.symbol for item in runtime.open_positions().positions] == ["ETHUSDT"]
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
            assert runtime.paper_state("ETHUSDT")["position_side"] == "Short"
        finally:
            runtime.close()


def test_account_inventory_projects_per_symbol_price_pnl_and_tick_size():
    with tempfile.TemporaryDirectory() as temp:
        primary = replace(_instrument(), tick_size=Decimal("0.10"))
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=StaticBookProvider(),
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(
                primary, symbol=symbol,
                tick_size=Decimal("0.10") if symbol == "BTCUSDT" else Decimal("0.01"),
            ),
        )
        try:
            opened = runtime.api.market(MarketCommandRequest(
                ClientActionId("inventory-pnl-btc"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            assert opened.status is CommandResultStatus.COMPLETED
            item = runtime.open_positions().positions[0]
            assert item.current_price == Decimal("64250.0")
            assert item.unrealized_pnl is not None
            assert item.tick_size == Decimal("0.10")
        finally:
            runtime.close()


def test_account_inventory_fails_closed_when_symbol_price_is_unavailable():
    with tempfile.TemporaryDirectory() as temp:
        provider = ToggleBookProvider()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=provider,
            instrument_snapshot=_instrument(),
            instrument_provider=lambda symbol: replace(_instrument(), symbol=symbol),
        )
        try:
            runtime.api.market(MarketCommandRequest(
                ClientActionId("inventory-no-price-eth"), "ETHUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            provider.unavailable_symbols.add("ETHUSDT")
            item = runtime.open_positions().positions[0]
            assert item.symbol == "ETHUSDT"
            assert item.current_price is None
            assert item.unrealized_pnl is None
        finally:
            runtime.close()


def test_account_inventory_fails_closed_when_symbol_price_is_stale():
    with tempfile.TemporaryDirectory() as temp:
        provider = ToggleBookProvider()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=provider,
            instrument_snapshot=_instrument(),
        )
        try:
            runtime.api.market(MarketCommandRequest(
                ClientActionId("inventory-stale-price"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            provider.stale_symbols.add("BTCUSDT")
            item = runtime.open_positions().positions[0]
            assert item.current_price is None
            assert item.unrealized_pnl is None
        finally:
            runtime.close()


def test_close_all_uses_stable_children_and_does_not_duplicate_closes():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for symbol, action in (("BTCUSDT", "bulk-open-btc"), ("ETHUSDT", "bulk-open-eth")):
                runtime.api.market(MarketCommandRequest(
                    ClientActionId(action), symbol, OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                ))
            request = CloseAllCommandRequest(ClientActionId("bulk-close-1"))
            first = runtime.close_all(request)
            execution_count = len(runtime.store.load_executions())
            second = runtime.close_all(request)

            assert first.positions == ()
            assert second.positions == ()
            assert len(first.results) == 2
            assert len(runtime.store.load_executions()) == execution_count
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
            assert runtime.paper_state("ETHUSDT")["position_side"] == "Flat"
        finally:
            runtime.close()


def _open_robot_position(runtime, *, candidate_id, trade_id, symbol="BTCUSDT"):
    account_id = TradingAccountId("paper")
    candidate, _ = runtime.store.create_robot_candidate(
        candidate_id=candidate_id,
        trading_account_id=account_id,
        symbol=Symbol(symbol),
        status="APPROVED",
        signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge"},
        approved_at_ms=1000,
        updated_at_ms=1000,
    )
    runtime.store.create_robot_trade(
        trade_id=trade_id,
        trading_account_id=account_id,
        candidate_id=candidate.candidate_id,
        symbol=Symbol(symbol),
        direction="LONG",
        pattern="Falling Wedge",
        source_timeframe="1",
        signal_time_ms=10,
        entry_time_ms=20,
        entry_path="MARKET",
        actual_wv=Decimal("1"),
        average_entry=Decimal("64250"),
        stop_price=Decimal("60000"),
        take_price=Decimal("70000"),
        entry_quantity=Decimal("1"),
        entry_position_version=1,
        created_at_ms=1001,
    )


def test_robot_close_all_only_closes_robot_owned_positions():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            for symbol, action in (("BTCUSDT", "robot-open-btc"), ("ETHUSDT", "manual-open-eth")):
                runtime.api.market(MarketCommandRequest(
                    ClientActionId(action), symbol, OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                    "Percent", Decimal("0.5"),
                ))
            _open_robot_position(runtime, candidate_id="candidate-btc", trade_id="trade-btc")

            request = CloseAllCommandRequest(ClientActionId("robot-bulk-close-1"))
            response = runtime.robot_close_all(request)

            assert len(response.results) == 1
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
            assert runtime.paper_state("ETHUSDT")["position_side"] != "Flat"
        finally:
            runtime.close()


def test_robot_close_all_marks_reconciliation_required_on_unconfirmed_close():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            runtime.api.market(MarketCommandRequest(
                ClientActionId("robot-open-btc-2"), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
                "Percent", Decimal("0.5"),
            ))
            _open_robot_position(runtime, candidate_id="candidate-btc-2", trade_id="trade-btc-2")

            account_id = TradingAccountId("paper")
            # PaperRuntime.__init__ already ran its own recovery pass with a
            # real wall-clock updated_at_ms; match that scale here so this
            # update's monotonic-timestamp check does not spuriously fail.
            now_ms = int(__import__("time").time() * 1000)
            running = runtime.store.get_robot_runtime_state(account_id)
            runtime.store.update_robot_runtime_state(
                account_id, mode="ROBOT_RUNNING", recovery_status="READY", reason=None,
                expected_version=running.version, updated_at_ms=now_ms,
            )

            rejected = CommandResult(
                "robot-close-all-x", CommandResultStatus.REJECTED, "exchange_rejected", "rejected",
            )
            with patch.object(runtime.api, "full_close", return_value=rejected):
                runtime.robot_close_all(CloseAllCommandRequest(ClientActionId("robot-bulk-close-2")))

            state = runtime.store.get_robot_runtime_state(account_id)
            assert state.mode == "ROBOT_RUNNING"
            assert state.recovery_status == "RECONCILIATION_REQUIRED"
        finally:
            runtime.close()


import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for test in (
            test_composed_paper_runtime_market_buy_completes,
            test_full_close_uses_authoritative_remaining_quantity_and_flat_repeat_is_noop,
            test_full_close_closes_short_without_flipping_long,
            test_account_inventory_is_multi_symbol_and_close_is_symbol_scoped,
            test_account_inventory_projects_per_symbol_price_pnl_and_tick_size,
            test_account_inventory_fails_closed_when_symbol_price_is_unavailable,
            test_account_inventory_fails_closed_when_symbol_price_is_stale,
            test_close_all_uses_stable_children_and_does_not_duplicate_closes,
            test_paper_limit_create_is_durable_idempotent_and_cancel_is_safe,
            test_paper_sell_limit_uses_shared_sizing_and_gtc,
            test_paper_limit_amend_reprices_in_place_and_is_durable_idempotent,
            test_paper_limit_amend_missing_or_inactive_fails_closed,
        )
    )
