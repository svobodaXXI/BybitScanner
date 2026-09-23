"""Focused coverage for lifecycle-scoped Robot protection continuity loss.

CR-PAPER-PROTECTION-LIFECYCLE-001.md section 22.4 slice C: an ``ingress_overflow``
whose only affected Robot lifecycle is a pre-entry LIMIT with independently proven
zero exposure cancels/terminalizes that one candidate instead of fencing the whole
Robot. Every uncertain or exposed shape keeps the existing global fail-closed fence.

All evidence is read on the serialized PAPER owner from the durable store; a cached
coverage role is never treated as proof. Each test uses its own temporary SQLite
database and never touches a production database, network, server or process.
"""

import tempfile
import time
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId,
    CommandResult,
    CommandResultStatus,
    LimitCommandRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
)
from terminal.domain.models import (
    Category, OrderSide, PositionKey, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_http_server import RobotProtectionCoverageManager
from terminal.runtime.paper_runtime import (
    CONTINUITY_ENTRY_ONLY_TERMINALIZED,
    CONTINUITY_FENCED,
    PaperRuntime,
    RobotPaperActionExecutor,
)

ACCOUNT = TradingAccountId("paper")
SYMBOL = "BTCUSDT"
OVERFLOW = "ingress_overflow"


class _Book:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=int(time.time() * 1000),
            available_depth=1,
        )


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR, SYMBOL, "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )


def _runtime(path: Path) -> PaperRuntime:
    primary = _instrument()
    runtime = PaperRuntime(
        path,
        book_provider=_Book(),
        instrument_snapshot=primary,
        instrument_provider=lambda symbol: replace(primary, symbol=symbol),
    )
    runtime._robot_command_dispatcher = lambda operation: operation(runtime)
    state = runtime.store.get_robot_runtime_state(ACCOUNT)
    runtime.store.update_robot_runtime_state(
        ACCOUNT, mode="ROBOT_RUNNING", recovery_status="READY", reason=None,
        expected_version=state.version, updated_at_ms=state.updated_at_ms + 1,
    )
    return runtime


@contextmanager
def _paper_runtime():
    """Isolated temporary database; always closed before the directory is removed."""
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime(Path(temp) / 'paper.sqlite3')
        try:
            yield runtime
        finally:
            runtime.close()


def _resting_entry(runtime: PaperRuntime, *, candidate_id: str, price: str) -> str:
    """One APPROVED candidate whose entry LIMIT rests unfilled (no crossing)."""
    executor = RobotPaperActionExecutor(runtime)
    submitted = executor.create_limit(LimitCommandRequest(
        ClientActionId(f"{candidate_id}-limit"), SYMBOL, OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal("321")),
        Decimal(price), Decimal(price), TimeInForce.GTC,
    ))
    assert submitted.status is CommandResultStatus.COMPLETED
    order_id = runtime.store.load_active_paper_limits(
        ACCOUNT, Symbol(SYMBOL))[-1].order_id.value
    runtime.store.create_robot_candidate(
        candidate_id=candidate_id, trading_account_id=ACCOUNT,
        symbol=Symbol(SYMBOL), status="APPROVED",
        signal_snapshot={
            "symbol": SYMBOL, "pattern": "Falling Wedge", "lifecycle": candidate_id,
        },
        approved_at_ms=1000, updated_at_ms=1000,
    )
    candidate = runtime.store.get_robot_candidate(candidate_id)
    runtime.store.save_robot_candidate_state(
        candidate_id, status="APPROVED",
        robot_state={"execution": {"limit_order_id": order_id}},
        expected_revision=candidate.state_revision, updated_at_ms=1100,
    )
    return order_id


def _runtime_state(runtime: PaperRuntime):
    return runtime.store.get_robot_runtime_state(ACCOUNT)


def test_proven_zero_fill_entry_is_terminalized_without_a_global_fence() -> None:
    with _paper_runtime() as runtime:
        order_id = _resting_entry(runtime, candidate_id="cand-zero", price="60000")

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_ENTRY_ONLY_TERMINALIZED
        state = _runtime_state(runtime)
        assert (state.mode, state.recovery_status) == ("ROBOT_RUNNING", "READY")
        assert state.reason is None
        order = runtime.store.get_paper_limit(order_id, ACCOUNT)
        assert order.status == "cancelled"
        assert order.filled_quantity == 0
        candidate = runtime.store.get_robot_candidate("cand-zero")
        assert candidate.status == "INVALIDATED"
        execution = candidate.robot_state["execution"]
        assert execution["stopped_without_entry_reason"] == (
            "robot_protection_entry_only_continuity_loss"
        )
        assert execution["continuity_loss_reason"] == OVERFLOW


def test_partial_fill_keeps_the_global_fence() -> None:
    with _paper_runtime() as runtime:
        # A crossing price fills the entry LIMIT on the owner thread.
        _resting_entry(runtime, candidate_id="cand-filled", price="64251")
        assert runtime.robot_match_symbol(SYMBOL) == 1

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_FENCED
        state = _runtime_state(runtime)
        assert (state.mode, state.recovery_status) == (
            "ROBOT_RUNNING", "RECONCILIATION_REQUIRED",
        )
        assert runtime.store.get_robot_candidate("cand-filled").status == "APPROVED"


def test_queued_fill_observed_before_resolution_keeps_the_global_fence() -> None:
    """The owner queue is FIFO: work queued before the resolution has run."""
    with _paper_runtime() as runtime:
        _resting_entry(runtime, candidate_id="cand-queued", price="64251")

        queued = [
            lambda owner: owner.robot_match_symbol(SYMBOL),
            lambda owner: owner.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW),
        ]
        results = [operation(runtime) for operation in queued]

        assert results[0] == 1
        assert results[1] == CONTINUITY_FENCED
        state = _runtime_state(runtime)
        assert state.recovery_status == "RECONCILIATION_REQUIRED"


def test_unresolved_obligation_on_the_symbol_keeps_the_global_fence() -> None:
    with _paper_runtime() as runtime:
        _resting_entry(runtime, candidate_id="cand-obligation", price="60000")
        _seed_open_trade_with_obligation(runtime, trade_id="trade-obligation")

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_FENCED
        assert _runtime_state(runtime).recovery_status == "RECONCILIATION_REQUIRED"
        assert runtime.store.get_robot_candidate("cand-obligation").status == "APPROVED"


def test_ambiguous_multiple_open_trades_keep_the_global_fence() -> None:
    """``get_open_robot_trade_for_symbol`` returns None for 0 and for >1 trades."""
    with _paper_runtime() as runtime:
        _resting_entry(runtime, candidate_id="cand-ambiguous", price="60000")
        _seed_open_trade(runtime, trade_id="trade-a")
        _seed_open_trade(runtime, trade_id="trade-b")

        assert runtime.store.get_open_robot_trade_for_symbol(
            ACCOUNT, Symbol(SYMBOL)) is None
        assert len(runtime.store.load_open_robot_trades(ACCOUNT)) == 2

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_FENCED
        assert _runtime_state(runtime).recovery_status == "RECONCILIATION_REQUIRED"


def test_cancellation_failure_keeps_the_global_fence() -> None:
    with _paper_runtime() as runtime:
        order_id = _resting_entry(runtime, candidate_id="cand-cancel", price="60000")
        runtime._robot_cancel_limit = lambda request: CommandResult(
            request.client_action_id.value, CommandResultStatus.REJECTED,
            "cancel_unavailable", "cancel unavailable",
        )

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_FENCED
        assert _runtime_state(runtime).recovery_status == "RECONCILIATION_REQUIRED"
        assert runtime.store.get_paper_limit(order_id, ACCOUNT).status == "open"
        assert runtime.store.get_robot_candidate("cand-cancel").status == "APPROVED"


def test_second_lifecycle_on_the_symbol_keeps_the_global_fence() -> None:
    with _paper_runtime() as runtime:
        _resting_entry(runtime, candidate_id="cand-first", price="60000")
        _resting_entry(runtime, candidate_id="cand-second", price="59000")

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_FENCED
        assert _runtime_state(runtime).recovery_status == "RECONCILIATION_REQUIRED"
        assert runtime.store.get_robot_candidate("cand-first").status == "APPROVED"
        assert runtime.store.get_robot_candidate("cand-second").status == "APPROVED"


def test_other_continuity_reasons_keep_the_global_fence() -> None:
    with _paper_runtime() as runtime:
        _resting_entry(runtime, candidate_id="cand-other", price="60000")

        outcome = runtime.resolve_robot_protection_continuity_loss(
            SYMBOL, "stale_generation_discarded")

        assert outcome == CONTINUITY_FENCED
        assert _runtime_state(runtime).recovery_status == "RECONCILIATION_REQUIRED"
        assert runtime.store.get_robot_candidate("cand-other").status == "APPROVED"


def test_no_robot_lifecycle_on_the_symbol_keeps_the_global_fence() -> None:
    with _paper_runtime() as runtime:

        outcome = runtime.resolve_robot_protection_continuity_loss(SYMBOL, OVERFLOW)

        assert outcome == CONTINUITY_FENCED
        assert _runtime_state(runtime).recovery_status == "RECONCILIATION_REQUIRED"


def _seed_open_trade(runtime: PaperRuntime, *, trade_id: str) -> None:
    runtime.store.create_robot_candidate(
        candidate_id=f"{trade_id}-cand", trading_account_id=ACCOUNT,
        symbol=Symbol(SYMBOL), status="APPROVED",
        signal_snapshot={
            "symbol": SYMBOL, "pattern": "Falling Wedge", "lifecycle": trade_id,
        },
        approved_at_ms=900, updated_at_ms=900,
    )
    runtime.store.create_robot_trade(
        trade_id=trade_id, trading_account_id=ACCOUNT,
        candidate_id=f"{trade_id}-cand", symbol=Symbol(SYMBOL), direction="LONG",
        pattern="Falling Wedge", source_timeframe="1", signal_time_ms=900,
        entry_time_ms=1000, entry_path="LIMIT", actual_wv=Decimal("0.8"),
        average_entry=Decimal("64000"), stop_price=Decimal("63000"),
        take_price=Decimal("65000"), created_at_ms=1000,
        entry_quantity=Decimal("0.005"), entry_position_version=1,
    )


def _seed_open_trade_with_obligation(runtime: PaperRuntime, *, trade_id: str) -> None:
    _seed_open_trade(runtime, trade_id=trade_id)
    runtime.store.latch_paper_protection_obligation(
        trade_id=trade_id, protection_version=1, winning_leg="STOP",
        trigger_price=Decimal("63000"), observed_exit_price=Decimal("63000"),
        observed_quantity=Decimal("0.005"), market_event_id=f"{SYMBOL}:1:1",
        source_received_at_ms=1200, source_generation=1, source_sequence=1,
        source_update_id=1, source_event_at_ms=1200,
        source_matching_engine_cts_ms=1200,
        observed_bid_price=Decimal("63000"), observed_ask_price=Decimal("63001"),
        latched_at_ms=1200,
    )


class _EntryOnlyOwner:
    """Owner double whose durable evidence proves a zero-exposure entry lifecycle."""

    def __init__(self) -> None:
        self.fence_calls: list[tuple[str, str]] = []
        self.resolve_calls: list[tuple[str, str]] = []
        self.coverage_symbols: tuple[str, ...] = (SYMBOL,)

    def robot_protection_coverage_symbols(self):
        return self.coverage_symbols

    def robot_protection_coverage_roles(self):
        return {symbol: "ENTRY_PENDING" for symbol in self.coverage_symbols}

    def robot_protection_continuity_loss(self):
        return None

    def fence_robot_protection_continuity_loss(self, symbol, reason):
        self.fence_calls.append((symbol, reason))
        return True

    def resolve_robot_protection_continuity_loss(self, symbol, reason):
        self.resolve_calls.append((symbol, reason))
        return CONTINUITY_ENTRY_ONLY_TERMINALIZED


class _DirectRuntime:
    def __init__(self, owner: _EntryOnlyOwner) -> None:
        self.owner = owner

    def call(self, operation, timeout=15.0):
        return operation(self.owner)

    def enqueue(self, operation, *, symbol=None, coverage_role=None):
        return operation(self.owner)


class _Hub:
    def subscribe(self, symbol):
        raise AssertionError("no market-data subscription is needed in this test")

    def discard(self, context):
        return None


def test_resync_after_proven_entry_only_terminalization_does_not_fence() -> None:
    owner = _EntryOnlyOwner()
    manager = RobotProtectionCoverageManager(
        _Hub(), _DirectRuntime(owner), recovery_session=object(),
    )

    manager._mark_unhealthy(SYMBOL, OVERFLOW)

    assert owner.resolve_calls == [(SYMBOL, OVERFLOW)]
    assert owner.fence_calls == []
    assert manager.is_healthy()

    # The terminalized lifecycle no longer needs coverage, so resync drops it
    # and must not impose a global fence on the way out.
    owner.coverage_symbols = ()
    manager.resync()

    assert owner.fence_calls == []
    assert manager.health()["unhealthy_symbols"] == {}
