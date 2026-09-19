import itertools
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
    Category, ExecutionDedupKey, ExecutionId, OrderId, OrderSide, PositionKey, PositionSide,
    Price, Quantity, Symbol,
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

            amended = executor.amend_limit(PaperLimitAmendRequest(
                ClientActionId("robot-limit-amend"),
                "BTCUSDT",
                submitted.order_id,
                Decimal("64251"),
            ))
            assert amended.status is CommandResultStatus.COMPLETED
            assert amended.order_id == submitted.order_id
            assert runtime.store.get_paper_limit(
                submitted.order_id, TradingAccountId("paper")
            ).price == Decimal("64251")

            applied = runtime.robot_match_symbol("BTCUSDT")
            assert applied == 1

            manager.activate(paper_account.id)
            state = runtime.paper_state("BTCUSDT")
            assert state["position_side"] == "Long"
            assert Decimal(state["position_quantity"]) > 0
        finally:
            runtime.close()


def test_robot_close_all_and_synchronize_pending_entries_independent_of_ui_selected_account():
    """P0.1 (CR-ROBOT-SAFETY-P0-001, AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md
    v1.6 Section 9): reproduces the pause_robot()/close_all_now() defect
    observed in live PAPER runtime -- robot_synchronize_pending_entries() and
    robot_close_all() raising live_mutations_disabled purely because the
    Workspace UI had a non-PAPER account selected -- and proves the fix.
    Mirrors test_robot_paper_execution_is_independent_of_ui_selected_account
    above: the UI-facing mutation path stays fenced exactly as before, while
    Robot's own safety reconciliation and Robot-owned close are unaffected by
    UI account selection. Does not touch operator command legality (the
    durable robot_runtime_state matrix in terminal.application.robot_control,
    exercised unchanged by tests/test_robot_control.py) at all."""

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
        try:
            # An OPEN Robot position (for robot_close_all) and a still-pending
            # candidate with a resting entry LIMIT (for
            # robot_synchronize_pending_entries), both seeded while the
            # Workspace UI is still on the PAPER account -- exactly as they
            # would already exist in production before an operator ever
            # switches the Workspace to a LIVE account.
            _open_robot_position(runtime, candidate_id="candidate-btc", trade_id="trade-btc", symbol="BTCUSDT")
            _seed_pending_candidate_with_resting_limit(
                runtime, candidate_id="candidate-eth", order_id="pending-eth-1", symbol="ETHUSDT",
            )
            _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")

            # Operator switches the Workspace UI to a live Bybit account --
            # exactly the reproduced production trigger.
            manager.activate(live_account.id)

            # Sibling UI-facing mutation stays fenced exactly as before.
            with pytest.raises(RuntimeError, match="live_mutations_disabled"):
                runtime.full_close(FullCloseCommandRequest(ClientActionId("ui-close"), "BTCUSDT"))

            # Robot's own synchronous safety reconciliation must still run:
            # this used to raise live_mutations_disabled here.
            sync_response = runtime.robot_synchronize_pending_entries()
            assert "pending-eth-1" in sync_response.cancelled_order_ids
            order = runtime.store.get_paper_limit("pending-eth-1", TradingAccountId("paper"))
            assert order.status == "cancelled"

            # Robot-owned close_all_now() must still execute and must still
            # act through the Robot-scoped (UI-independent) execution port,
            # not the Workspace-scoped one.
            close_response = runtime.robot_close_all(
                CloseAllCommandRequest(ClientActionId("robot-close-live"))
            )
            assert len(close_response.results) == 1
            assert close_response.results[0].status is CommandResultStatus.COMPLETED

            manager.activate(paper_account.id)
            assert runtime.paper_state("BTCUSDT")["position_side"] == "Flat"
        finally:
            runtime.close()


_crossing_book_sequence = itertools.count(1)


def _crossing_book(symbol: str, *, bid: str, ask: str) -> NormalizedOrderBook:
    now_ms = int(__import__("time").time() * 1000)
    sequence = next(_crossing_book_sequence)
    return NormalizedOrderBook(
        symbol=Symbol(symbol),
        bids=(PriceLevel(Price(Decimal(bid)), Quantity(Decimal("1"))),),
        asks=(PriceLevel(Price(Decimal(ask)), Quantity(Decimal("1"))),),
        health=BookHealth.READY,
        # Fresh real time -- D2.3 dispatch may feed this same book straight
        # into PaperMarketExecutor.execute(), which fails closed on a stale
        # (max_book_age_ms) book; a fixed historical timestamp would make
        # every real close attempt in these tests spuriously stale.
        received_at_ms=now_ms,
        available_depth=1,
        # D2.4 immutable event identity: the fresh-crossing gate in
        # PaperRuntime fails closed when any of these is None. A single
        # WS connection (generation 0) with a monotonically increasing
        # sequence/update_id mirrors real Bybit delivery; matching-engine
        # cts is legitimately optional (not every message carries it).
        source_generation=0,
        source_sequence=sequence,
        source_update_id=sequence,
        source_event_at_ms=now_ms,
        source_matching_engine_cts_ms=None,
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


def test_robot_reconcile_accepts_tick_normalized_protection_prices():
    """Reconciliation compares the durable normalized protection, not raw strategy prices."""
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime,
                symbol="BTCUSDT",
                entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000.1"),
                take_price=Decimal("64600.1"),
                trade_id="trade-reconcile-normalized-protection",
                candidate_id="candidate-reconcile-normalized-protection",
            )

            position_key = PositionKey(
                TradingAccountId("paper"),
                Category.LINEAR,
                Symbol("BTCUSDT"),
                0,
            )
            protection = runtime.store.get_protection_projection(position_key)
            assert protection is not None
            assert protection.stop_loss == Decimal("64000.5")
            assert protection.take_profit == Decimal("64600.5")

            _set_admission(
                runtime,
                mode="ROBOT_RUNNING",
                recovery_status="RECONCILIATION_REQUIRED",
            )

            result = runtime.robot_reconcile()

            assert result.success is True
            assert result.unresolved_trade_ids == ()
            assert result.recovery_status == "PAUSED"
        finally:
            runtime.close()


def test_robot_reconcile_success_lands_paused_and_never_ready():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-reconcile-safe", candidate_id="candidate-reconcile-safe",
            )
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )

            result = runtime.robot_reconcile()

            assert result.success is True
            assert result.mode == "ROBOT_RUNNING"
            assert result.recovery_status == "PAUSED"
            assert runtime.robot_admission_ready() is False
            state = runtime.store.get_robot_runtime_state(TradingAccountId("paper"))
            assert state.recovery_status == "PAUSED"
        finally:
            runtime.close()


def test_robot_reconcile_closes_stale_trade_only_from_existing_execution_evidence():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-reconcile-evidence",
                candidate_id="candidate-reconcile-evidence",
            )
            position_key = PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            )
            quantity = runtime.store.get_position_projection(position_key).quantity.value
            latched, _ = runtime.store.latch_paper_protection_obligation(
                trade_id="trade-reconcile-evidence", protection_version=1,
                winning_leg="STOP", trigger_price=Decimal("64000"),
                observed_exit_price=Decimal("63990"), observed_quantity=quantity,
                market_event_id="evt-reconcile-evidence", source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"),
                observed_ask_price=Decimal("63995"), latched_at_ms=4000,
            )
            claimed = runtime.store.transition_paper_protection_obligation(
                latched.obligation_id, expected_status="TRIGGERED",
                next_status="DISPATCHING", expected_version=latched.version,
                updated_at_ms=4001,
            )
            close_book = _crossing_book("BTCUSDT", bid="63990", ask="63995")
            provider.set_book("BTCUSDT", close_book)
            runtime._market_executor.execute(
                trading_account_id=TradingAccountId("paper"), symbol=Symbol("BTCUSDT"),
                side=OrderSide.SELL, quantity=Quantity(quantity),
                order_link_id=claimed.obligation_id, order_id=claimed.order_id,
                exec_id=claimed.exec_id,
            )
            assert runtime.store.get_robot_trade("trade-reconcile-evidence").exit_time_ms is None
            assert runtime.store.get_position_projection(position_key).side is PositionSide.FLAT
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )

            result = runtime.robot_reconcile()

            assert result.success is True
            assert result.recovery_status == "PAUSED"
            assert result.closed_trade_ids == ("trade-reconcile-evidence",)
            closed = runtime.store.get_robot_trade("trade-reconcile-evidence")
            execution = runtime.store.get_execution(
                ExecutionDedupKey(TradingAccountId("paper"), Category.LINEAR, claimed.exec_id)
            )
            assert closed.exit_reason == "STOP"
            assert closed.exit_price == execution.price.value
            assert closed.exit_time_ms == execution.exchange_timestamp_ms
        finally:
            runtime.close()


def test_robot_reconcile_flat_stale_trade_without_attributable_evidence_stays_required():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-reconcile-missing-evidence",
                candidate_id="candidate-reconcile-missing-evidence",
            )
            manual = runtime.api.full_close(
                FullCloseCommandRequest(ClientActionId("manual-before-reconcile"), "BTCUSDT")
            )
            assert manual.status is CommandResultStatus.COMPLETED
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )
            executions_before = len(runtime.store.load_executions())

            result = runtime.robot_reconcile()

            assert result.success is False
            assert result.recovery_status == "RECONCILIATION_REQUIRED"
            assert result.unresolved_trade_ids == ("trade-reconcile-missing-evidence",)
            trade = runtime.store.get_robot_trade("trade-reconcile-missing-evidence")
            assert trade.exit_time_ms is None
            assert trade.exit_price is None
            assert trade.exit_reason is None
            assert len(runtime.store.load_executions()) == executions_before
        finally:
            runtime.close()


def _last_entry_order_id(runtime, symbol: str) -> str:
    executions = runtime.store.load_executions_for_symbol(
        TradingAccountId("paper"), Symbol(symbol),
    )
    return [item.order_id.value for item in executions if item.side is OrderSide.BUY][-1]


def _attach_robot_entry_state(
    runtime, *, candidate_id: str, status: str, order_id: str, updated_at_ms: int,
    emergency: dict | None = None,
):
    """Persist the candidate's own entry/emergency execution state.

    This is exactly the durable shape RobotBreakoutMonitor writes and the only
    place flat-closure attribution is allowed to read ownership from.
    """
    execution = {"limit_order_id": order_id}
    if emergency is not None:
        execution.update(emergency)
    candidate = runtime.store.get_robot_candidate(candidate_id)
    return runtime.store.save_robot_candidate_state(
        candidate_id, status=status, robot_state={"execution": execution},
        expected_revision=candidate.state_revision, updated_at_ms=updated_at_ms,
    )


def _flatten_symbol_with_colliding_robot_entry(
    runtime, *, symbol: str, entry_price: Decimal, trade_id: str,
    stale_candidate_id: str, colliding_candidate_id: str,
):
    """Reproduce the 0GUSDT shape: two Robot LIMIT lots, one aggregate close.

    Returns ``(trade, closing_execution, colliding_order_id)`` with the stale
    trade still OPEN against an authoritative FLAT position. The emergency
    marker is deliberately left to the caller.
    """
    _open_robot_position_with_confirmed_protection(
        runtime, symbol=symbol, entry_price=entry_price,
        stop_price=Decimal("64000"), take_price=Decimal("64600"),
        trade_id=trade_id, candidate_id=stale_candidate_id,
    )
    _attach_robot_entry_state(
        runtime, candidate_id=stale_candidate_id, status="OPEN",
        order_id=_last_entry_order_id(runtime, symbol), updated_at_ms=2000,
    )

    executor = RobotPaperActionExecutor(runtime)
    submitted = executor.create_limit(LimitCommandRequest(
        ClientActionId(f"{colliding_candidate_id}-limit"), symbol, OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal("321")),
        entry_price, entry_price, TimeInForce.GTC,
    ))
    assert submitted.status is CommandResultStatus.COMPLETED
    assert runtime.robot_match_symbol(symbol) == 1
    colliding_order_id = _last_entry_order_id(runtime, symbol)
    runtime.store.create_robot_candidate(
        candidate_id=colliding_candidate_id, trading_account_id=TradingAccountId("paper"),
        symbol=Symbol(symbol), status="APPROVED",
        signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge", "leg": "colliding"},
        approved_at_ms=1600, updated_at_ms=1600,
    )

    position_key = PositionKey(TradingAccountId("paper"), Category.LINEAR, Symbol(symbol), 0)
    aggregate = runtime.store.get_position_projection(position_key).quantity.value
    trade = runtime.store.get_robot_trade(trade_id)
    assert aggregate > trade.entry_quantity

    closed = runtime.api.full_close(FullCloseCommandRequest(
        ClientActionId(f"{trade_id}-aggregate-close"), symbol,
    ))
    assert closed.status is CommandResultStatus.COMPLETED
    assert runtime.store.get_position_projection(position_key).side is PositionSide.FLAT

    closing = runtime.store.load_executions_for_symbol(
        TradingAccountId("paper"), Symbol(symbol),
    )[-1]
    assert closing.side is OrderSide.SELL
    assert closing.quantity.value == aggregate
    assert runtime.store.get_robot_trade(trade_id).exit_time_ms is None
    return trade, closing, colliding_order_id


def test_robot_reconcile_terminalizes_stale_trade_flattened_by_aggregate_emergency_close():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            trade, closing, colliding_order_id = _flatten_symbol_with_colliding_robot_entry(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                trade_id="trade-flat-aggregate",
                stale_candidate_id="candidate-flat-aggregate",
                colliding_candidate_id="candidate-flat-colliding",
            )
            _attach_robot_entry_state(
                runtime, candidate_id="candidate-flat-colliding", status="INVALIDATED",
                order_id=colliding_order_id,
                updated_at_ms=closing.exchange_timestamp_ms,
                emergency={
                    "emergency_close_attempted_at_ms": closing.exchange_timestamp_ms - 1000,
                    "emergency_close_outcome": "CLOSED_EMERGENCY_PROTECTION_FAILURE",
                    "emergency_closed_at_ms": closing.exchange_timestamp_ms + 1000,
                },
            )
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )
            executions_before = len(runtime.store.load_executions())

            result = runtime.robot_reconcile()

            assert result.success is True
            assert result.recovery_status == "PAUSED"
            assert result.closed_trade_ids == ("trade-flat-aggregate",)
            assert result.unresolved_trade_ids == ()
            assert result.unresolved_candidate_ids == ()

            stale = runtime.store.get_robot_trade("trade-flat-aggregate")
            assert stale.exit_reason == "EMERGENCY_CLOSE"
            assert stale.exit_price == closing.price.value
            assert stale.exit_time_ms == closing.exchange_timestamp_ms
            assert stale.fees_costs_usdt == (
                closing.fee * trade.entry_quantity / closing.quantity.value
            )
            assert stale.realized_pnl_usdt == (
                trade.entry_quantity * (closing.price.value - trade.average_entry)
            )
            assert stale.realized_pnl_pct == (
                (stale.realized_pnl_usdt - stale.fees_costs_usdt)
                / (trade.entry_quantity * trade.average_entry) * 100
            )
            candidate = runtime.store.get_robot_candidate("candidate-flat-aggregate")
            assert candidate.status == "CLOSED"
            # Recovery reads durable rows only; it never mutates the ledger.
            assert len(runtime.store.load_executions()) == executions_before
        finally:
            runtime.close()


def test_robot_reconcile_flat_aggregate_close_without_emergency_marker_stays_required():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _, closing, colliding_order_id = _flatten_symbol_with_colliding_robot_entry(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                trade_id="trade-flat-no-marker",
                stale_candidate_id="candidate-flat-no-marker",
                colliding_candidate_id="candidate-flat-no-marker-colliding",
            )
            # Same aggregate close, same Robot-attributable lot -- but the
            # colliding candidate carries no durable emergency evidence, so the
            # closure has no proven cause.
            _attach_robot_entry_state(
                runtime, candidate_id="candidate-flat-no-marker-colliding",
                status="INVALIDATED", order_id=colliding_order_id,
                updated_at_ms=closing.exchange_timestamp_ms,
            )
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )
            executions_before = len(runtime.store.load_executions())

            result = runtime.robot_reconcile()

            assert result.success is False
            assert result.recovery_status == "RECONCILIATION_REQUIRED"
            assert result.unresolved_trade_ids == ("trade-flat-no-marker",)
            assert result.closed_trade_ids == ()
            trade = runtime.store.get_robot_trade("trade-flat-no-marker")
            assert trade.exit_time_ms is None
            assert trade.exit_price is None
            assert trade.exit_reason is None
            assert runtime.store.get_robot_candidate(
                "candidate-flat-no-marker"
            ).status == "OPEN"
            assert len(runtime.store.load_executions()) == executions_before
        finally:
            runtime.close()


def test_robot_reconcile_duplicate_owner_ambiguity_never_blind_closes_net_position():
    with tempfile.TemporaryDirectory() as temp:
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-reconcile-owner-a", candidate_id="candidate-reconcile-owner-a",
            )
            runtime.store.create_robot_candidate(
                candidate_id="candidate-reconcile-owner-b",
                trading_account_id=TradingAccountId("paper"), symbol=Symbol("BTCUSDT"),
                status="APPROVED", signal_snapshot={"symbol": "BTCUSDT", "pattern": "second"},
                approved_at_ms=1000, updated_at_ms=1000,
            )
            runtime.store.create_robot_trade(
                trade_id="trade-reconcile-owner-b", trading_account_id=TradingAccountId("paper"),
                candidate_id="candidate-reconcile-owner-b", symbol=Symbol("BTCUSDT"),
                direction="LONG", pattern="second", source_timeframe="1",
                signal_time_ms=900, entry_time_ms=1500, entry_path="LIMIT",
                actual_wv=Decimal("0.2"), average_entry=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                entry_quantity=Decimal("0.004"), entry_position_version=1, created_at_ms=1500,
            )
            runtime.store.latch_paper_protection_obligation(
                trade_id="trade-reconcile-owner-a", protection_version=1,
                winning_leg="STOP", trigger_price=Decimal("64000"),
                observed_exit_price=Decimal("63990"), observed_quantity=Decimal("0.004"),
                market_event_id="evt-duplicate-owner", source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
            )
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )
            executions_before = len(runtime.store.load_executions())
            position_before = runtime.store.get_position_projection(PositionKey(
                TradingAccountId("paper"), Category.LINEAR, Symbol("BTCUSDT"), 0,
            ))

            result = runtime.robot_reconcile()

            assert result.success is False
            assert result.recovery_status == "RECONCILIATION_REQUIRED"
            assert set(result.unresolved_candidate_ids) == {
                "candidate-reconcile-owner-a", "candidate-reconcile-owner-b",
            }
            position_after = runtime.store.get_position_projection(position_before.position_key)
            assert position_after == position_before
            assert len(runtime.store.load_executions()) == executions_before
            assert runtime.store.get_robot_trade("trade-reconcile-owner-a").exit_time_ms is None
            assert runtime.store.get_robot_trade("trade-reconcile-owner-b").exit_time_ms is None
            obligation = runtime.store.get_paper_protection_obligation_for_trade(
                "trade-reconcile-owner-a"
            )
            assert obligation.status == "TRIGGERED"
        finally:
            runtime.close()


def test_robot_reconcile_is_independent_of_workspace_live_account_selection():
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
        provider = MutableBookProvider("BTCUSDT", _entry_book())
        primary = _instrument()
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3", book_provider=provider,
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(primary, symbol=symbol),
            account_manager=manager,
        )
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        try:
            _open_robot_position_with_confirmed_protection(
                runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                stop_price=Decimal("64000"), take_price=Decimal("64600"),
                trade_id="trade-reconcile-live-ui", candidate_id="candidate-reconcile-live-ui",
            )
            _set_admission(
                runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
            )
            manager.activate(live_account.id)

            result = runtime.robot_reconcile()

            assert result.success is True
            assert result.recovery_status == "PAUSED"
            assert manager.active_account.id == live_account.id
        finally:
            runtime.close()


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


def test_retest_detected_candidate_is_covered_before_entry_limit_submission():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            account = TradingAccountId("paper")
            runtime.store.create_robot_candidate(
                candidate_id="candidate-prelimit-coverage", trading_account_id=account,
                symbol=Symbol("BTCUSDT"), status="APPROVED",
                signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
                approved_at_ms=1000, updated_at_ms=1000,
            )
            runtime.store.save_robot_candidate_state(
                "candidate-prelimit-coverage", status="APPROVED",
                robot_state={"phase": "RETEST_DETECTED", "execution": {}},
                expected_revision=0, updated_at_ms=1001,
            )
            assert runtime.robot_protection_coverage_symbols() == ("BTCUSDT",)
        finally:
            runtime.close()


def test_robot_entry_limit_is_covered_before_first_fill_and_released_after_zero_fill_cancel():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _seed_pending_candidate_with_resting_limit(
                runtime, candidate_id="candidate-entry-coverage",
                order_id="entry-coverage-limit", symbol="BTCUSDT",
            )
            assert runtime.robot_protection_coverage_symbols() == ("BTCUSDT",)

            runtime._robot_cancel_limit(PaperLimitCancelRequest(
                ClientActionId("entry-coverage-cancel"),
                "BTCUSDT", "entry-coverage-limit",
            ))
            assert runtime.robot_protection_coverage_symbols() == ()
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
                source_received_at_ms=2000,
                source_generation=0, source_sequence=2000, source_update_id=2000,
                source_event_at_ms=2000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("97.9"), observed_ask_price=Decimal("98.1"),
                latched_at_ms=2000,
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
                source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
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
                source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
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
                source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
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
                source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
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
                source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
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
                source_received_at_ms=4000,
                source_generation=0, source_sequence=4000, source_update_id=4000,
                source_event_at_ms=4000, source_matching_engine_cts_ms=None,
                observed_bid_price=Decimal("63990"), observed_ask_price=Decimal("63995"),
                latched_at_ms=4000,
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
            with patch.object(runtime._robot_api, "full_close", return_value=rejected):
                runtime.robot_close_all(CloseAllCommandRequest(ClientActionId("robot-bulk-close-2")))

            state = runtime.store.get_robot_runtime_state(account_id)
            assert state.mode == "ROBOT_RUNNING"
            assert state.recovery_status == "RECONCILIATION_REQUIRED"
        finally:
            runtime.close()


def _seed_pending_candidate_with_resting_limit(
    runtime, *, candidate_id, order_id, symbol="BTCUSDT",
):
    """Directly seed an APPROVED/RETEST_DETECTED candidate with a real
    resting paper_limit order already submitted -- bypasses the full
    breakout/retest state machine (unrelated to what these tests cover),
    mirroring _open_robot_position's existing direct-seed pattern above."""
    account_id = TradingAccountId("paper")
    runtime.store.create_paper_limit(
        client_action_id=f"seed-{order_id}",
        request_fingerprint=f"seed-fp-{order_id}",
        order_id=OrderId(order_id),
        order_link_id=f"seed-link-{order_id}",
        trading_account_id=account_id,
        symbol=Symbol(symbol),
        side=OrderSide.BUY,
        price=Decimal("64000"),
        quantity=Decimal("1"),
        created_at_ms=1000,
    )
    runtime.store.create_robot_candidate(
        candidate_id=candidate_id,
        trading_account_id=account_id,
        symbol=Symbol(symbol),
        status="APPROVED",
        signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge"},
        approved_at_ms=1000,
        updated_at_ms=1000,
    )
    runtime.store.save_robot_candidate_state(
        candidate_id, status="APPROVED",
        robot_state={"phase": "RETEST_DETECTED", "execution": {"limit_order_id": order_id}},
        expected_revision=0, updated_at_ms=1000,
    )


def _set_admission(runtime, *, mode, recovery_status):
    account_id = TradingAccountId("paper")
    running = runtime.store.get_robot_runtime_state(account_id)
    now_ms = int(__import__("time").time() * 1000)
    return runtime.store.update_robot_runtime_state(
        account_id, mode=mode, recovery_status=recovery_status, reason=None,
        expected_version=running.version, updated_at_ms=now_ms,
    )


def test_robot_synchronize_pending_entries_cancels_zero_fill_resting_limit_when_paused():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _seed_pending_candidate_with_resting_limit(
                runtime, candidate_id="candidate-btc", order_id="test-limit-1",
            )
            _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")

            response = runtime.robot_synchronize_pending_entries()

            assert response.unresolved_candidate_ids == ()
            assert "test-limit-1" in response.cancelled_order_ids
            order = runtime.store.get_paper_limit("test-limit-1", TradingAccountId("paper"))
            assert order.status == "cancelled"
            candidate = runtime.store.get_robot_candidate("candidate-btc")
            assert candidate.status == "APPROVED"  # recoverable, never invalidated by PAUSE
        finally:
            runtime.close()


def test_pause_race_book_update_after_cancellation_cannot_fill_the_cancelled_order():
    """Part E race scenario 1: a resting Robot entry LIMIT priced to cross
    the book immediately (BUY well above the static ask) must not fill via
    a book update that arrives AFTER robot_synchronize_pending_entries()
    has already cancelled it -- proving the synchronous cancel closes the
    PAUSE race rather than merely reporting success optimistically."""
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            account_id = TradingAccountId("paper")
            symbol = "BTCUSDT"
            runtime.store.create_paper_limit(
                client_action_id="seed-race-1",
                request_fingerprint="seed-race-fp-1",
                order_id=OrderId("test-limit-race-1"),
                order_link_id="seed-race-link-1",
                trading_account_id=account_id,
                symbol=Symbol(symbol),
                side=OrderSide.BUY,
                price=Decimal("70000"),  # comfortably above the static ask (64250.5)
                quantity=Decimal("1"),
                created_at_ms=1000,
            )
            runtime.store.create_robot_candidate(
                candidate_id="candidate-race",
                trading_account_id=account_id,
                symbol=Symbol(symbol),
                status="APPROVED",
                signal_snapshot={"symbol": symbol, "pattern": "Falling Wedge"},
                approved_at_ms=1000,
                updated_at_ms=1000,
            )
            runtime.store.save_robot_candidate_state(
                "candidate-race", status="APPROVED",
                robot_state={
                    "phase": "RETEST_DETECTED",
                    "execution": {"limit_order_id": "test-limit-race-1"},
                },
                expected_revision=0, updated_at_ms=1000,
            )
            _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")

            response = runtime.robot_synchronize_pending_entries()
            assert "test-limit-race-1" in response.cancelled_order_ids

            # A book update arriving right after PAUSE's synchronous cancel
            # must not be able to fill the now-cancelled order.
            runtime.robot_match_symbol(symbol)

            order = runtime.store.get_paper_limit("test-limit-race-1", account_id)
            assert order.status == "cancelled"
            position_key = PositionKey(account_id, Category.LINEAR, Symbol(symbol), 0)
            projection = runtime.store.get_position_projection(position_key)
            assert projection is None or projection.quantity.value == 0
        finally:
            runtime.close()


def test_robot_synchronize_pending_entries_terminalizes_zero_exposure_candidate_when_stopped():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _seed_pending_candidate_with_resting_limit(
                runtime, candidate_id="candidate-btc", order_id="test-limit-2",
            )
            _set_admission(runtime, mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")

            response = runtime.robot_synchronize_pending_entries()

            assert response.unresolved_candidate_ids == ()
            assert "candidate-btc" in response.terminalized_candidate_ids
            candidate = runtime.store.get_robot_candidate("candidate-btc")
            assert candidate.status == "INVALIDATED"
        finally:
            runtime.close()


def test_robot_synchronize_pending_entries_reports_unresolved_on_cancel_failure():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _seed_pending_candidate_with_resting_limit(
                runtime, candidate_id="candidate-btc", order_id="test-limit-3",
            )
            _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")

            with patch.object(
                runtime.store, "cancel_paper_limit", side_effect=RuntimeError("boom"),
            ):
                response = runtime.robot_synchronize_pending_entries()

            assert "candidate-btc" in response.unresolved_candidate_ids
            order = runtime.store.get_paper_limit("test-limit-3", TradingAccountId("paper"))
            assert order.status != "cancelled"
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


def test_robot_market_event_skips_fill_finalization_when_no_limit_execution():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        book = StaticBookProvider().get_book(Symbol("BTCUSDT"))
        try:
            with patch("terminal.runtime.paper_runtime.RobotBreakoutMonitor") as monitor:
                finalized, obligation = runtime.process_robot_market_event(
                    "BTCUSDT",
                    book,
                    event_id="BTCUSDT:no-fill",
                    received_at_ms=book.received_at_ms,
                )

            assert finalized == ()
            assert obligation is None
            monitor.assert_not_called()
        finally:
            runtime.close()


def _legacy_coverage_roles(runtime) -> dict[str, str]:
    """Verbatim copy of robot_protection_coverage_roles before the light read."""
    from terminal.runtime.paper_runtime import INACTIVE_LIMIT_STATUSES

    account = TradingAccountId("paper")
    candidates = runtime.store.load_robot_candidates(account)
    roles = {
        candidate.symbol.value: "EXPOSURE"
        for candidate in candidates
        if candidate.status == "OPEN"
    }
    for obligation in runtime.store.load_unresolved_paper_protection_obligations(account):
        roles[obligation.symbol.value] = "OBLIGATION"
    for candidate in candidates:
        if candidate.status != "APPROVED" or candidate.robot_state is None:
            continue
        if candidate.robot_state.get("phase") != "RETEST_DETECTED":
            continue
        execution = candidate.robot_state.get("execution") or {}
        order_id = execution.get("limit_order_id")
        needs_coverage = not order_id
        if order_id:
            order = runtime.store.get_paper_limit(order_id, account)
            needs_coverage = (
                order is not None
                and (
                    order.status not in INACTIVE_LIMIT_STATUSES
                    or order.filled_quantity > 0
                )
            )
        if needs_coverage:
            roles.setdefault(candidate.symbol.value, "ENTRY_PENDING")
    return dict(sorted(roles.items()))


def _seed_candidate(runtime, candidate_id, symbol, *, state=None, final_status=None, snapshot=None):
    runtime.store.create_robot_candidate(
        candidate_id=candidate_id, trading_account_id=TradingAccountId("paper"),
        symbol=Symbol(symbol), status="APPROVED",
        signal_snapshot=snapshot or {"symbol": symbol, "pattern": "Falling Wedge"},
        approved_at_ms=1000, updated_at_ms=1000,
    )
    revision = 0
    if state is not None:
        runtime.store.save_robot_candidate_state(
            candidate_id, status="APPROVED", robot_state=state,
            expected_revision=revision, updated_at_ms=1001,
        )
        revision += 1
    if final_status is not None:
        runtime.store.save_robot_candidate_state(
            candidate_id, status=final_status, robot_state=state or {"phase": final_status},
            expected_revision=revision, updated_at_ms=1002,
        )


def _seed_mixed_coverage_fixture(runtime) -> None:
    account = TradingAccountId("paper")
    retest = {"phase": "RETEST_DETECTED", "execution": {}}
    # OPEN -> EXPOSURE
    _open_robot_position_with_confirmed_protection(
        runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
        stop_price=Decimal("64000"), take_price=Decimal("64600"),
        trade_id="trade-mixed-open", candidate_id="candidate-mixed-open",
    )
    # Closed trade (candidate CLOSED) with an unresolved obligation -> OBLIGATION
    _seed_candidate(runtime, "candidate-mixed-obligation", "ETHUSDT")
    runtime.store.create_robot_trade(
        trade_id="trade-mixed-obligation", trading_account_id=account,
        candidate_id="candidate-mixed-obligation", symbol=Symbol("ETHUSDT"),
        direction="LONG", pattern="Falling Wedge", source_timeframe="1",
        signal_time_ms=900, entry_time_ms=1500, entry_path="LIMIT",
        actual_wv=Decimal("0.8"), average_entry=Decimal("100"),
        stop_price=Decimal("98"), take_price=Decimal("104"),
        entry_quantity=Decimal("1"), entry_position_version=1, created_at_ms=1500,
    )
    runtime.store.latch_paper_protection_obligation(
        trade_id="trade-mixed-obligation", protection_version=1, winning_leg="STOP",
        trigger_price=Decimal("98"), observed_exit_price=Decimal("97.9"),
        observed_quantity=Decimal("1"), market_event_id="evt-mixed",
        source_received_at_ms=2000,
        source_generation=0, source_sequence=2000, source_update_id=2000,
        source_event_at_ms=2000, source_matching_engine_cts_ms=None,
        observed_bid_price=Decimal("97.9"), observed_ask_price=Decimal("98.1"),
        latched_at_ms=2000,
    )
    runtime.store.close_robot_trade(
        "trade-mixed-obligation", exit_time_ms=3000, exit_price=Decimal("98"),
        exit_reason="STOP", realized_pnl_usdt=Decimal("-2"),
        realized_pnl_pct=Decimal("-2"), fees_costs_usdt=Decimal("0.1"),
        updated_at_ms=3000,
    )
    # RETEST_DETECTED with a resting entry LIMIT / with no LIMIT yet -> ENTRY_PENDING
    _seed_pending_candidate_with_resting_limit(
        runtime, candidate_id="candidate-mixed-limit", order_id="mixed-limit", symbol="SOLUSDT",
    )
    _seed_candidate(runtime, "candidate-mixed-prelimit", "XRPUSDT", state=retest)
    # Not covered: unknown LIMIT, still waiting for breakout, no state yet
    _seed_candidate(
        runtime, "candidate-mixed-unknown-limit", "ADAUSDT",
        state={"phase": "RETEST_DETECTED", "execution": {"limit_order_id": "missing"}},
    )
    _seed_candidate(runtime, "candidate-mixed-waiting", "DOGEUSDT", state={"phase": "WAITING_BREAKOUT"})
    _seed_candidate(runtime, "candidate-mixed-no-state", "LTCUSDT")
    # Finished RETEST_DETECTED candidates must stay uncovered
    _seed_candidate(runtime, "candidate-mixed-expired", "AVAXUSDT", state=retest, final_status="EXPIRED")
    _seed_candidate(
        runtime, "candidate-mixed-invalidated", "LINKUSDT", state=retest, final_status="INVALIDATED",
    )


def test_coverage_roles_from_light_read_match_the_previous_full_read():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _seed_mixed_coverage_fixture(runtime)
            statuses = {
                item.candidate_id: item.status
                for item in runtime.store.load_robot_candidates(TradingAccountId("paper"))
            }
            assert statuses["candidate-mixed-open"] == "OPEN"
            assert statuses["candidate-mixed-obligation"] == "CLOSED"

            roles = runtime.robot_protection_coverage_roles()
            assert roles == _legacy_coverage_roles(runtime)
            assert roles == {
                "BTCUSDT": "EXPOSURE",
                "ETHUSDT": "OBLIGATION",
                "SOLUSDT": "ENTRY_PENDING",
                "XRPUSDT": "ENTRY_PENDING",
            }
            assert runtime.robot_protection_coverage_symbols() == tuple(roles)
        finally:
            runtime.close()


def test_active_candidate_states_skip_finished_rows_and_never_read_the_snapshot():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            _seed_mixed_coverage_fixture(runtime)
            account = TradingAccountId("paper")
            # Break every snapshot: the full read must now fail, the light read must not.
            runtime.store._connection.execute(
                "UPDATE robot_candidates SET signal_snapshot_json='not json'"
            )
            with pytest.raises(Exception):
                runtime.store.load_robot_candidates(account)

            states = runtime.store.load_active_robot_candidate_states(account)
            assert {item.candidate_id: item.status for item in states} == {
                "candidate-mixed-open": "OPEN",
                "candidate-mixed-limit": "APPROVED",
                "candidate-mixed-prelimit": "APPROVED",
                "candidate-mixed-unknown-limit": "APPROVED",
                "candidate-mixed-waiting": "APPROVED",
                "candidate-mixed-no-state": "APPROVED",
            }
            by_id = {item.candidate_id: item for item in states}
            assert by_id["candidate-mixed-limit"].symbol == Symbol("SOLUSDT")
            assert by_id["candidate-mixed-limit"].robot_state == {
                "phase": "RETEST_DETECTED", "execution": {"limit_order_id": "mixed-limit"},
            }
            assert by_id["candidate-mixed-no-state"].robot_state is None
            assert not hasattr(by_id["candidate-mixed-open"], "signal_snapshot")
        finally:
            runtime.close()


def test_coverage_roles_do_not_parse_finished_candidate_history():
    import terminal.persistence.sqlite_store as sqlite_store

    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            big_snapshot = {"symbol": "OLDUSDT", "pattern": "Falling Wedge", "pad": "x" * 20_000}
            for index in range(300):
                _seed_candidate(
                    runtime, f"candidate-history-{index}", "OLDUSDT",
                    state={"phase": "RETEST_DETECTED", "execution": {}},
                    final_status=("EXPIRED", "INVALIDATED")[index % 2],
                    snapshot={**big_snapshot, "n": index},  # snapshot hashes are unique
                )
            _seed_candidate(
                runtime, "candidate-live", "XRPUSDT",
                state={"phase": "RETEST_DETECTED", "execution": {}},
            )

            with patch.object(
                sqlite_store, "_robot_candidate_from_row",
                side_effect=AssertionError("full candidate row parsed"),
            ), patch.object(
                sqlite_store, "_robot_candidate_state_from_row",
                wraps=sqlite_store._robot_candidate_state_from_row,
            ) as light_rows:
                assert runtime.robot_protection_coverage_roles() == {"XRPUSDT": "ENTRY_PENDING"}
            assert light_rows.call_count == 1
        finally:
            runtime.close()


_CACHE_SYMBOLS = ("AUSDT", "BUSDT", "CUSDT", "DUSDT", "EUSDT")


def _runtime_with_candle_cache(path: Path, fetch):
    from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider

    primary = _instrument()
    return PaperRuntime(
        path,
        book_provider=StaticBookProvider(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
        robot_closed_candle_provider=CachedClosedCandleProvider(fetch),
        # Fixed geometry index so reconcile's recovery policy reaches the synchronization.
        robot_latest_geometry_index_provider=lambda *args: 101,
    )


def _seed_waiting_candidates(runtime) -> None:
    # WAITING_BREAKOUT: every synchronization tick reads a closed candle per candidate.
    import robot_state_machine
    from test_robot_breakout_monitor import _snapshot

    for index, symbol in enumerate(_CACHE_SYMBOLS):
        candidate_id = f"candidate-cache-{index}"
        snapshot = _snapshot(symbol=symbol)
        state, _ = robot_state_machine.initialize_state({
            "candidate_id": candidate_id, "status": "APPROVED", "timeframe": "1",
            "signal_snapshot": snapshot,
        })
        assert state["phase"] == robot_state_machine.PHASE_WAITING_BREAKOUT
        runtime.store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=TradingAccountId("paper"),
            symbol=Symbol(symbol), status="APPROVED", signal_snapshot=snapshot,
            approved_at_ms=1000, updated_at_ms=1000,
        )
        runtime.store.save_robot_candidate_state(
            candidate_id, status="APPROVED", robot_state=state,
            expected_revision=0, updated_at_ms=1001,
        )


def _run_robot_command(runtime, command: str) -> None:
    if command == "pause":
        _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")
        runtime.robot_synchronize_pending_entries()
    elif command == "stop":
        _set_admission(runtime, mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        runtime.robot_synchronize_pending_entries()
    else:
        _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        runtime.robot_reconcile()


@pytest.mark.parametrize("command", ["pause", "stop", "reconcile"])
def test_robot_commands_with_warm_candle_cache_do_no_network_on_owner_thread(command):
    import threading

    calls = []

    def fetch(symbol):
        calls.append((symbol, threading.get_ident()))
        return {"time_ms": 60_000, "high": 1.0, "low": 1.0, "close": 1.0}

    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_with_candle_cache(Path(temp) / "paper.sqlite3", fetch)
        try:
            owner = threading.get_ident()  # this runtime's SQLiteStore owner
            _seed_waiting_candidates(runtime)
            assert runtime.robot_approved_candidate_symbols() == _CACHE_SYMBOLS

            # Warm-up happens off the owner thread (as the HTTP handler does it).
            warm = threading.Thread(
                target=runtime.robot_closed_candle_cache.warm, args=(_CACHE_SYMBOLS,),
            )
            warm.start()
            warm.join(timeout=10)
            assert len(calls) == 5 and all(ident != owner for _, ident in calls)

            _run_robot_command(runtime, command)

            assert [symbol for symbol, ident in calls if ident == owner] == []
            assert runtime.robot_closed_candle_cache.metrics()["candle_cache_misses_owner"] == 0
        finally:
            runtime.close()


@pytest.mark.parametrize("command", ["pause", "stop", "reconcile"])
def test_robot_commands_without_warm_cache_still_fetch_on_owner_thread_as_before(command):
    import threading

    calls = []

    def fetch(symbol):
        calls.append((symbol, threading.get_ident()))
        return {"time_ms": 60_000, "high": 1.0, "low": 1.0, "close": 1.0}

    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_with_candle_cache(Path(temp) / "paper.sqlite3", fetch)
        try:
            _seed_waiting_candidates(runtime)
            _run_robot_command(runtime, command)
            # Fallback: the previous in-place fetch, one per candidate.
            assert sorted(symbol for symbol, _ in calls) == list(_CACHE_SYMBOLS)
            assert all(ident == threading.get_ident() for _, ident in calls)
            assert runtime.robot_closed_candle_cache.metrics() == {
                "candle_cache_hits": 0, "candle_cache_misses_owner": 5,
            }
        finally:
            runtime.close()


def test_default_candle_cache_keeps_admission_catchup_enabled():
    from scanner_geometry_cursor import latest_scanner_closed_candle, load_scanner_catchup_closed_candles
    from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider

    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / "paper.sqlite3")
        try:
            cache = runtime.robot_closed_candle_cache
            assert isinstance(cache, CachedClosedCandleProvider)
            assert cache.fetch is latest_scanner_closed_candle
            monitor = runtime._robot_breakout_monitor
            assert monitor._get_closed_candle is cache
            # Same as before: the bare default provider switched catch-up on.
            assert monitor._get_admission_catchup_candles is load_scanner_catchup_closed_candles
        finally:
            runtime.close()
