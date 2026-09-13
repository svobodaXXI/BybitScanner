"""Production-topology regression: Robot PAPER execution must dispatch every
mutation and match back onto PaperRuntime's single owning writer thread.

RobotBreakoutMonitor always runs on its own background thread
("robot-breakout-monitor"). In production, PaperRuntime (and the SQLiteStore/
TradingApplication/ExecutionEngine graph it owns) is constructed on a
SEPARATE, single "paper-runtime-owner" thread inside SerializedPaperRuntime.
Every prior test exercised RobotBreakoutMonitor either with a fake action
executor (no real SQLiteStore) or against a bare PaperRuntime driven
synchronously on the SAME thread as the test -- neither reproduces this
topology, which is exactly why this regression (SQLiteStore's cross-thread
guard raising "must be used by its owning writer thread") went unnoticed.
"""

from __future__ import annotations

import threading
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import robot_state_machine
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountProvider,
    TradingAccountStatus, paper_account_manager,
)
from terminal.domain.models import Category, Price, PositionKey, Quantity, Symbol, TradingAccountId
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from terminal.runtime.paper_http_server import SerializedPaperRuntime, create_configured_paper_runtime
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT_ID = TradingAccountId("paper")
LIVE_ACCOUNT_ID = "bybit-live-1"
SYMBOL = "TESTUSDT"
T0_MS = 1_800_000
ROBOT_TICK_INTERVAL_S = 0.03
POLL_TIMEOUT_S = 5.0


def _instrument(symbol: str = SYMBOL) -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR, symbol, "LinearPerpetual", "Trading",
        "TEST", "USDT", "USDT", Decimal("0.1"), Decimal("1000000"),
        Decimal("0.1"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )


def _snapshot(symbol: str = SYMBOL, *, apex_index: int = 300, current_index: int = 100) -> dict:
    return {
        "symbol": symbol,
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": current_index,
            "touches": {
                "lower_touch_points": [{"price": 80.0, "counted": True}, {"price": 82.0, "counted": True}],
                "upper_touch_points": [{"price": 150.0, "counted": True}, {"price": 152.0, "counted": True}],
            },
            "pair_metrics": {"reference_price": 100.0, "start_width": 20.0},
        },
        "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
            geometry_index=current_index, source_candle_time_ms=T0_MS, timeframe="1",
        ),
    }


def _retest_detected_state(*, retest_index: int = 103, breakout_index: int = 101) -> dict:
    return {
        "state_version": robot_state_machine.STATE_VERSION,
        "phase": robot_state_machine.PHASE_RETEST_DETECTED,
        "pattern": "Falling Wedge",
        "direction": robot_state_machine.DIRECTION_LONG,
        "geometry_cursor": retest_index,
        "breakout_index": breakout_index,
        "retest_index": retest_index,
        "last_event": robot_state_machine.EVENT_RETEST,
    }


def _candle_at(index: int, *, high: float, low: float, close: float) -> dict:
    return {"time_ms": T0_MS + (index - 100) * 60_000, "high": high, "low": low, "close": close}


class _FixedCandleProvider:
    """Thread-safe: called from the real "robot-breakout-monitor" thread."""

    def __init__(self, symbol: str, candle: dict):
        self._symbol = symbol
        self._candle = candle
        self._lock = threading.Lock()
        self.calls: list[str] = []

    def __call__(self, symbol: str):
        with self._lock:
            self.calls.append(symbol)
        return self._candle if symbol == self._symbol else None


class _MutableBookProvider:
    """Deliberately has NO "currently displayed" buffer (get_current_book_update
    always returns None) -- Robot matching must go through get_book()'s
    REST-fallback-shaped path independent of any live UI buffer/symbol."""

    def __init__(self):
        self._lock = threading.Lock()
        self._book: tuple[str, Decimal, Decimal] | None = None

    def set(self, symbol: str, *, bid: Decimal, ask: Decimal) -> None:
        with self._lock:
            self._book = (symbol, bid, ask)

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        with self._lock:
            book = self._book
        if book is None or book[0] != symbol.value:
            return None
        _, bid, ask = book
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(bid), Quantity(Decimal("1000"))),),
            asks=(PriceLevel(Price(ask), Quantity(Decimal("1000"))),),
            health=BookHealth.READY, received_at_ms=int(time.time() * 1000), available_depth=1,
        )

    def get_current_book_update(self, symbol: Symbol):
        return None


class _PoisonLiveAdapterFactory:
    """Fails loudly if ever invoked -- proves Robot PAPER execution never
    reaches a LIVE mutation/read adapter, even while the active Workspace
    account is a live Bybit account."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("LIVE adapter factory must never be called during Robot PAPER execution")


def _account_manager_with_live_bybit() -> "TradingAccountManager":
    manager = paper_account_manager()
    manager.register_inactive(TradingAccount(
        TradingAccountId(LIVE_ACCOUNT_ID), "Live Mainnet", TradingAccountProvider.BYBIT,
        TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
    ))
    return manager


def _publish_live_snapshot(database_path: Path) -> None:
    store = LiveAccountProjectionStore(database_path.with_suffix(".live_accounts.sqlite3"))
    store.publish(LiveAccountSnapshot(
        LIVE_ACCOUNT_ID, "MAINNET", False, 1, Decimal("1000"), Decimal("1000"),
        Decimal("1000"), 1, (), (), 1,
    ))
    store.close()


def _build_runtime(
    database_path: Path, *, book_provider, candle_provider, live_adapter_factory,
) -> SerializedPaperRuntime:
    instrument = _instrument()
    return SerializedPaperRuntime(lambda: create_configured_paper_runtime(
        database_path,
        book_provider=book_provider,
        instrument_snapshot=instrument,
        instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
        account_manager=_account_manager_with_live_bybit(),
        live_adapter_factory=live_adapter_factory,
        live_mutation_adapter_factory=live_adapter_factory,
        robot_closed_candle_provider=candle_provider,
        robot_tick_interval_s=ROBOT_TICK_INTERVAL_S,
    ))


def _activate_live_account(runtime: SerializedPaperRuntime) -> None:
    """Simulate the operator switching the Workspace UI to a live Bybit
    account AFTER the backend is already running -- the exact real-world
    sequence that exposed both this bug and the earlier account-fencing one."""
    runtime.call(lambda owner: owner.activate_account(
        LIVE_ACCOUNT_ID,
        owner._account_manager.session_token.active_account_id.value,
        owner._account_manager.session_token.generation,
    ))


def _seed_retest_detected_candidate(runtime: SerializedPaperRuntime, candidate_id: str, symbol: str) -> None:
    def seed(owner: PaperRuntime) -> None:
        owner.store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=ACCOUNT_ID, symbol=Symbol(symbol),
            status="APPROVED", signal_snapshot=_snapshot(symbol), approved_at_ms=1, updated_at_ms=1,
        )
        owner.store.save_robot_candidate_state(
            candidate_id, status="APPROVED", robot_state=_retest_detected_state(),
            expected_revision=0, updated_at_ms=1,
        )
    runtime.call(seed)


def _wait_until(predicate, *, timeout=POLL_TIMEOUT_S, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condition was not met within the timeout")


class RobotPaperExecutionThreadingTests(unittest.TestCase):
    def test_a_b_c_d_f_real_topology_limit_fill_and_protection_dispatch_to_owner_thread(self):
        with __import__("tempfile").TemporaryDirectory() as temp:
            database_path = Path(temp) / "paper.sqlite3"
            _publish_live_snapshot(database_path)

            book = _MutableBookProvider()
            book.set(SYMBOL, bid=Decimal("1000000"), ask=Decimal("1000001"))  # far: no fill yet
            candle = _FixedCandleProvider(SYMBOL, _candle_at(150, high=99, low=97, close=98))
            poison = _PoisonLiveAdapterFactory()

            runtime = _build_runtime(
                database_path, book_provider=book, candle_provider=candle,
                live_adapter_factory=poison,
            )
            try:
                owner_ident = runtime.call(lambda owner: threading.get_ident())

                # A: active Workspace account = BYBIT LIVE.
                _activate_live_account(runtime)
                active = runtime.call(lambda owner: owner._account_manager.active_account.provider.value)
                self.assertEqual(active, "BYBIT")

                _seed_retest_detected_candidate(runtime, "candidate-1", SYMBOL)

                # B: instrument PaperRuntime._robot_create_limit to record the
                # thread it actually executes on, proving Robot's mutation
                # lands on the SAME thread that owns PaperRuntime.store --
                # never robot-breakout-monitor's own thread.
                recorded_idents: list[int] = []
                original_robot_create_limit = PaperRuntime._robot_create_limit

                def instrumented(self, request):
                    recorded_idents.append(threading.get_ident())
                    return original_robot_create_limit(self, request)

                with patch.object(PaperRuntime, "_robot_create_limit", instrumented):
                    runtime.start_robot_monitor()

                    # A: no "owning writer thread" exception; PAPER LIMIT durably created.
                    def limit_submitted():
                        current = runtime.call(lambda owner: owner.store.get_robot_candidate("candidate-1"))
                        execution = (current.robot_state or {}).get("execution") or {}
                        if execution.get("last_execution_error"):
                            raise AssertionError(
                                f"candidate failed instead of submitting: {execution}"
                            )
                        return current if execution.get("limit_order_id") else None

                    record = _wait_until(limit_submitted)
                    order_id = record.robot_state["execution"]["limit_order_id"]

                self.assertTrue(recorded_idents, "instrumented _robot_create_limit was never called")
                self.assertTrue(
                    all(ident == owner_ident for ident in recorded_idents),
                    "Robot LIMIT submission ran off PaperRuntime's owning thread",
                )

                orders = runtime.call(
                    lambda owner: owner.store.load_active_paper_limits(ACCOUNT_ID, Symbol(SYMBOL))
                )
                self.assertEqual(len(orders), 1)
                self.assertEqual(orders[0].order_id.value, order_id)
                limit_price = orders[0].price

                # C: cross the book so the resting PAPER LIMIT can fill --
                # matching must reach it via robot_match_symbol()'s
                # get_book()-based dispatch, independent of any live-streamed
                # "workspace symbol" buffer (get_current_book_update() always
                # returns None on this fixture).
                book.set(SYMBOL, bid=limit_price - Decimal("1"), ask=limit_price - Decimal("0.1"))

                def filled():
                    order = runtime.call(
                        lambda owner: owner.store.get_paper_limit(order_id, ACCOUNT_ID)
                    )
                    return order if order is not None and order.status == "filled" else None

                _wait_until(filled)

                # D: entry fill -> STOP/TAKE protection creation, also
                # dispatched through the owner thread (create_stop/create_take
                # go through the same _dispatch_robot_command() path).
                def protected():
                    position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
                    protection = runtime.call(
                        lambda owner: owner.store.get_protection_projection(position_key)
                    )
                    return protection if (
                        protection is not None
                        and (protection.stop_loss is not None or protection.take_profit is not None)
                    ) else None

                _wait_until(protected)

                # create_robot_trade() (which flips the candidate to OPEN) runs
                # via RobotBreakoutMonitor's OWN separate connection, slightly
                # after the protection projection above becomes visible on
                # PaperRuntime's connection -- poll rather than assert immediately.
                def candidate_open():
                    trades = runtime.call(lambda owner: owner.store.load_robot_candidates(ACCOUNT_ID))
                    candidate = next(c for c in trades if c.candidate_id == "candidate-1")
                    return candidate if candidate.status == "OPEN" else None

                _wait_until(candidate_open)

                # F: zero LIVE mutation/read adapter calls throughout, despite
                # the active Workspace account being a live Bybit account.
                self.assertEqual(poison.calls, 0)
            finally:
                runtime.close()

    def test_g_restart_with_stale_retest_detected_creates_exactly_one_order(self):
        """A second SerializedPaperRuntime instance pointed at the same
        durable database (simulating a process restart) must not duplicate
        the order for a candidate already mid-submission -- ClientActionId
        determinism plus create_paper_limit's fingerprint/idempotency must
        survive the full real-topology dispatch path, not just direct calls."""

        with __import__("tempfile").TemporaryDirectory() as temp:
            database_path = Path(temp) / "paper.sqlite3"
            _publish_live_snapshot(database_path)
            book = _MutableBookProvider()
            book.set(SYMBOL, bid=Decimal("1000000"), ask=Decimal("1000001"))
            candle = _FixedCandleProvider(SYMBOL, _candle_at(150, high=99, low=97, close=98))

            runtime = _build_runtime(
                database_path, book_provider=book, candle_provider=candle,
                live_adapter_factory=_PoisonLiveAdapterFactory(),
            )
            try:
                _seed_retest_detected_candidate(runtime, "candidate-1", SYMBOL)
                runtime.start_robot_monitor()

                def limit_submitted():
                    current = runtime.call(lambda owner: owner.store.get_robot_candidate("candidate-1"))
                    execution = (current.robot_state or {}).get("execution") or {}
                    return current if execution.get("limit_order_id") else None

                _wait_until(limit_submitted)
            finally:
                runtime.close()

            # Restart: a fresh SerializedPaperRuntime/PaperRuntime/
            # RobotBreakoutMonitor over the SAME durable database.
            restarted = _build_runtime(
                database_path, book_provider=book, candle_provider=candle,
                live_adapter_factory=_PoisonLiveAdapterFactory(),
            )
            try:
                restarted.start_robot_monitor()
                time.sleep(ROBOT_TICK_INTERVAL_S * 5)
                orders = restarted.call(
                    lambda owner: owner.store.load_active_paper_limits(ACCOUNT_ID, Symbol(SYMBOL))
                )
                self.assertEqual(len(orders), 1)
            finally:
                restarted.close()


if __name__ == "__main__":
    unittest.main()
