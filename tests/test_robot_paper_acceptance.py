"""Deterministic production-path PAPER acceptance for Robot v0.1.

The test drives the real durable admission gate, breakout/retest state machine,
serialized PaperRuntime command path, resting PAPER LIMIT matching, Robot trade
creation and protection. Only market inputs are synthetic; no exchange/network
access or fake action executor is used.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import types
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import robot_state_machine
from robot_candidate_store import create_signal_snapshot
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.application.robot_admission import admit_robot_candidate
from terminal.application.robot_control import start_robot
from terminal.application.trading_accounts import paper_account_manager
from terminal.domain.models import Category, Price, PositionKey, Quantity, Symbol, TradingAccountId
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel

# PaperRuntime imports ``main`` only to bind ScannerControlRuntime.run_scan_pass.
# This acceptance never starts Scanner, and a clean CI checkout intentionally
# has no gitignored config.py. Stub only that inert scanner entrypoint so the
# Robot PAPER topology remains importable without machine-local credentials.
_scanner_entrypoint = types.ModuleType("main")
_scanner_entrypoint.run_scan_pass = lambda: None
sys.modules.setdefault("main", _scanner_entrypoint)

from terminal.runtime.paper_http_server import SerializedPaperRuntime, create_configured_paper_runtime


ACCOUNT_ID = TradingAccountId("paper")
SYMBOL = "ACCEPTUSDT"
CANDIDATE_ID = "deterministic-paper-acceptance"
T0_MS = 1_800_000
TICK_INTERVAL_S = 0.02
POLL_TIMEOUT_S = 4.0


def _instrument(symbol: str = SYMBOL) -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR, symbol, "LinearPerpetual", "Trading",
        "ACCEPT", "USDT", "USDT", Decimal("0.1"), Decimal("1000000"),
        Decimal("0.1"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )


def _snapshot() -> dict:
    current_index = 100
    return {
        "symbol": SYMBOL,
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 300, "price": 90.0, "valid_intersection": True},
            "current_index": current_index,
            "touches": {
                "lower_touch_points": [
                    {"price": 80.0, "counted": True},
                    {"price": 82.0, "counted": True},
                ],
                "upper_touch_points": [
                    {"price": 150.0, "counted": True},
                    {"price": 152.0, "counted": True},
                ],
            },
            "pair_metrics": {"reference_price": 100.0, "start_width": 20.0},
        },
        "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
            geometry_index=current_index,
            source_candle_time_ms=T0_MS,
            timeframe="1",
        ),
    }


def _candle(index: int, *, high: float, low: float, close: float) -> dict:
    return {
        "time_ms": T0_MS + (index - 100) * 60_000,
        "high": high,
        "low": low,
        "close": close,
    }


class _DeterministicCandleProvider:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._candle: dict | None = None

    def set(self, candle: dict | None) -> None:
        with self._lock:
            self._candle = candle

    def __call__(self, symbol: str):
        with self._lock:
            candle = self._candle
        return candle if symbol == SYMBOL else None


class _MutableBookProvider:
    def __init__(self) -> None:
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
            health=BookHealth.READY,
            received_at_ms=int(time.time() * 1000),
            available_depth=1,
        )

    def get_current_book_update(self, symbol: Symbol):
        return None


def _fixed_geometry_index_provider(symbol: str, signal_snapshot) -> int:
    if symbol != SYMBOL:
        raise AssertionError(f"unexpected symbol: {symbol}")
    return 103


def _wait_until(predicate, *, timeout: float = POLL_TIMEOUT_S, interval: float = 0.01):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condition was not met within {timeout:.1f}s; last={last!r}")


class RobotPaperDeterministicAcceptanceTests(unittest.TestCase):
    def test_admission_breakout_retest_limit_fill_trade_and_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database_path = root / "paper.sqlite3"
            candidate_dir = root / "candidates"
            instrument = _instrument()
            candles = _DeterministicCandleProvider()
            book = _MutableBookProvider()
            book.set(SYMBOL, bid=Decimal("80"), ask=Decimal("120"))

            runtime = SerializedPaperRuntime(lambda: create_configured_paper_runtime(
                database_path,
                book_provider=book,
                instrument_snapshot=instrument,
                instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
                account_manager=paper_account_manager(),
                robot_closed_candle_provider=candles,
                robot_latest_geometry_index_provider=_fixed_geometry_index_provider,
                robot_tick_interval_s=TICK_INTERVAL_S,
            ))
            try:
                started = start_robot(database_path=database_path)
                self.assertEqual((started.mode, started.recovery_status), ("ROBOT_RUNNING", "READY"))

                create_signal_snapshot(
                    _snapshot(),
                    timeframe="1",
                    store_dir=candidate_dir,
                    candidate_id=CANDIDATE_ID,
                    created_at="2026-09-15T00:00:00+00:00",
                )
                admitted, created = admit_robot_candidate(
                    CANDIDATE_ID,
                    approval={"source": "deterministic-paper-acceptance"},
                    database_path=database_path,
                    store_dir=candidate_dir,
                )
                self.assertTrue(created)
                self.assertEqual(admitted.status, "APPROVED")
                self.assertIsNone(admitted.robot_state)

                runtime.start_robot_monitor()

                def candidate_record():
                    return runtime.call(lambda owner: owner.store.get_robot_candidate(CANDIDATE_ID))

                def phase(expected: str):
                    record = candidate_record()
                    state = (record.robot_state or {}) if record is not None else {}
                    error = (state.get("execution") or {}).get("last_execution_error")
                    if error:
                        raise AssertionError(f"Robot execution failed: {error}")
                    return record if state.get("phase") == expected else None

                _wait_until(lambda: phase(robot_state_machine.PHASE_WAITING_BREAKOUT))

                # Deterministic breakout above the frozen upper wedge boundary.
                candles.set(_candle(102, high=106, low=97, close=105))
                _wait_until(lambda: phase(robot_state_machine.PHASE_WAITING_RETEST))

                # Deterministic retest: low touches/crosses the same frozen boundary.
                candles.set(_candle(103, high=101, low=95, close=98))
                _wait_until(lambda: phase(robot_state_machine.PHASE_RETEST_DETECTED))

                def limit_submitted():
                    record = candidate_record()
                    execution = ((record.robot_state or {}).get("execution") or {}) if record else {}
                    if execution.get("last_execution_error"):
                        raise AssertionError(f"Robot LIMIT submission failed: {execution}")
                    return execution.get("limit_order_id")

                order_id = _wait_until(limit_submitted)
                order = runtime.call(lambda owner: owner.store.get_paper_limit(order_id, ACCOUNT_ID))
                self.assertIsNotNone(order)
                self.assertEqual(order.status, "open")

                # Cross the deterministic book through the real PAPER matcher.
                book.set(
                    SYMBOL,
                    bid=order.price - Decimal("1"),
                    ask=order.price - Decimal("0.1"),
                )

                def open_trade():
                    return runtime.call(
                        lambda owner: owner.store.get_open_robot_trade_for_symbol(
                            ACCOUNT_ID, Symbol(SYMBOL)
                        )
                    )

                trade = _wait_until(open_trade)
                self.assertEqual(trade.candidate_id, CANDIDATE_ID)
                self.assertEqual(trade.entry_path, "LIMIT")
                self.assertGreater(trade.entry_quantity, 0)

                position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)

                def active_protection():
                    projection = runtime.call(
                        lambda owner: owner.store.get_protection_projection(position_key)
                    )
                    if projection is None or projection.stop_loss is None:
                        return None
                    return projection

                protection = _wait_until(active_protection)
                self.assertIsNotNone(protection.stop_loss)

                final_candidate = _wait_until(
                    lambda: (
                        record
                        if (record := candidate_record()) is not None and record.status == "OPEN"
                        else None
                    )
                )
                self.assertEqual(final_candidate.status, "OPEN")
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
