"""Deterministic production-path PAPER acceptance for Robot v0.1.

The test drives the real durable admission gate, breakout/retest state machine,
serialized PaperRuntime command path, resting PAPER LIMIT matching, Robot trade
creation and protection. Only market inputs are synthetic; no exchange/network
access or fake action executor is used.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import robot_state_machine
from robot_candidate_store import create_signal_snapshot
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.api.models import (
    ClientActionId, CommandResultStatus, MarketCommandRequest, PaperStopDeleteRequest,
    VolumeRequest, VolumeUnit,
)
from terminal.application.normalization import normalize_limit_price
from terminal.application.robot_admission import admit_robot_candidate
from terminal.application.robot_admission_catchup import replay_admission_catchup
from terminal.application.robot_control import start_robot
from terminal.application.trading_accounts import paper_account_manager
from terminal.domain.models import (
    Category, CommandId, OrderSide, Price, PositionKey, Quantity, Symbol, TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel

# Importing the PAPER/Robot topology must not require Scanner config.py.

from terminal.runtime.paper_http_server import SerializedPaperRuntime, create_configured_paper_runtime


ACCOUNT_ID = TradingAccountId("paper")
SYMBOL = "ACCEPTUSDT"
CANDIDATE_ID = "deterministic-paper-acceptance"
T0_MS = 1_800_000
TICK_INTERVAL_S = 0.02
POLL_TIMEOUT_S = 4.0
_event_sequence = 0


def _event_book(symbol: str, *, bid: Decimal, ask: Decimal) -> NormalizedOrderBook:
    global _event_sequence
    _event_sequence += 1
    now_ms = int(time.time() * 1000)
    return NormalizedOrderBook(
        symbol=Symbol(symbol),
        bids=(PriceLevel(Price(bid), Quantity(Decimal("1000"))),),
        asks=(PriceLevel(Price(ask), Quantity(Decimal("1000"))),),
        health=BookHealth.READY,
        received_at_ms=now_ms,
        available_depth=1,
        source_generation=0,
        source_sequence=_event_sequence,
        source_update_id=_event_sequence,
        source_event_at_ms=now_ms,
        source_matching_engine_cts_ms=None,
    )


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
    def test_late_admission_market_entry_protection_and_restart_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "paper.sqlite3"
            candidate_dir = Path(temp) / "candidates"
            instrument = _instrument()
            candles = _DeterministicCandleProvider()
            candles.set(_candle(103, high=101, low=95, close=98))
            position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
            protection_observations = []
            ticks = []

            class DepthBook(_MutableBookProvider):
                def get_book(self, symbol):
                    # Fresh deterministic depth; actual VWAP differs from the
                    # Scanner reference and top ask, exercising post-fill math.
                    return replace(
                        _event_book(symbol.value, bid=Decimal("99.9"), ask=Decimal("100")),
                        asks=(
                            PriceLevel(Price(Decimal("100")), Quantity(Decimal("1"))),
                            PriceLevel(Price(Decimal("100.2")), Quantity(Decimal("1000"))),
                        ),
                        available_depth=2,
                    )

            def factory():
                owner = create_configured_paper_runtime(
                    database_path,
                    book_provider=DepthBook(),
                    instrument_snapshot=instrument,
                    instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
                    account_manager=paper_account_manager(),
                    robot_closed_candle_provider=candles,
                    robot_latest_geometry_index_provider=_fixed_geometry_index_provider,
                    robot_tick_interval_s=TICK_INTERVAL_S,
                )
                # Observe ordering, but delegate every protection mutation to
                # the real runtime. No market submitter/executor is replaced.
                for name in ("_robot_create_stop", "_robot_create_take"):
                    original = getattr(owner, name)

                    def observed(request, original=original, name=name):
                        executions = owner.store.load_executions()
                        position = owner.store.get_position_projection(position_key)
                        self.assertEqual(len(executions), 1)
                        self.assertIsNotNone(position.average_entry)
                        protection_observations.append((name, position.average_entry.value))
                        return original(request)

                    setattr(owner, name, observed)
                original_tick = owner._robot_breakout_monitor.tick

                def counted_tick():
                    result = original_tick()
                    ticks.append(threading.get_ident())
                    return result

                owner._robot_breakout_monitor.tick = counted_tick
                return owner

            runtime = SerializedPaperRuntime(factory)
            try:
                start_robot(database_path=database_path)
                snapshot = _snapshot()
                create_signal_snapshot(
                    snapshot, timeframe="1", store_dir=candidate_dir,
                    candidate_id=CANDIDATE_ID, created_at="2026-09-15T00:00:00+00:00",
                )
                admitted, created = admit_robot_candidate(
                    CANDIDATE_ID, approval={"source": "late-paper-acceptance"},
                    database_path=database_path, store_dir=candidate_dir,
                )
                self.assertTrue(created)
                initial, _ = robot_state_machine.initialize_state({
                    "status": "APPROVED", "timeframe": "1", "signal_snapshot": snapshot,
                })
                late_state, _ = replay_admission_catchup(snapshot, initial, (
                    {"closed": True, "timeframe": "1", "geometry_index": 102,
                     "high": 106, "low": 97, "close": 105},
                    {"closed": True, "timeframe": "1", "geometry_index": 103,
                     "high": 101, "low": 95, "close": 98},
                ))
                self.assertEqual(late_state["execution"]["entry_mode"], "LATE_ADMISSION_MARKET")
                runtime.call(lambda owner: owner.store.save_robot_candidate_state(
                    CANDIDATE_ID, status="APPROVED", robot_state=late_state,
                    expected_revision=admitted.state_revision, updated_at_ms=int(time.time() * 1000),
                ))
                self.assertEqual(runtime.call(lambda owner: owner.store.load_executions()), ())
                runtime.start_robot_monitor()

                def open_trade():
                    return runtime.call(lambda owner: owner.store.get_open_robot_trade_for_symbol(
                        ACCOUNT_ID, Symbol(SYMBOL),
                    ))

                trade = _wait_until(open_trade)
                self.assertEqual(trade.entry_path, "MARKET")
                self.assertGreater(trade.entry_quantity, Decimal("1"))
                expected_vwap = (
                    Decimal("100") + (trade.entry_quantity - 1) * Decimal("100.2")
                ) / trade.entry_quantity
                self.assertEqual(trade.average_entry, expected_vwap)
                self.assertGreater(expected_vwap, Decimal("100"))
                # The structural STOP is >2% away, so the existing fallback
                # proves protection was rebuilt from actual entry, not top ask.
                self.assertEqual(trade.stop_price, expected_vwap * Decimal("0.98"))
                self.assertEqual(trade.take_price, Decimal("118"))
                self.assertEqual(protection_observations, [
                    ("_robot_create_stop", expected_vwap),
                    ("_robot_create_take", expected_vwap),
                ])

                def durable_evidence(owner):
                    candidate = owner.store.get_robot_candidate(CANDIDATE_ID)
                    intent = candidate.robot_state["execution"]["late_market_intent"]
                    command = owner.store.get_command(CommandId(intent["command_id"]))
                    count = owner.store._connection.execute(
                        "SELECT COUNT(*) FROM trading_commands WHERE command_kind = 'create_market'"
                    ).fetchone()[0]
                    return (
                        command, count, owner.store.load_executions(),
                        owner.store.get_position_projection(position_key),
                        owner.store.get_protection_projection(position_key),
                    )

                before = runtime.call(durable_evidence)
                command, count, executions, position, protection = before
                self.assertEqual(count, 1)
                self.assertEqual(command.current_state, CommandState.FILLED)
                self.assertEqual(len(executions), 1)
                self.assertEqual(position.average_entry.value, expected_vwap)
                # protection.stop_loss/take_profit are the executable PAPER
                # order prices: trade.stop_price/take_price (the raw
                # strategy-plan values) tick-normalized on the position's
                # closing side, same as production protection submission.
                closing_side = (
                    OrderSide.SELL
                    if trade.direction == robot_state_machine.DIRECTION_LONG
                    else OrderSide.BUY
                )
                self.assertEqual(
                    protection.stop_loss,
                    normalize_limit_price(trade.stop_price, instrument.tick_size, closing_side),
                )
                self.assertEqual(
                    protection.take_profit,
                    normalize_limit_price(trade.take_price, instrument.tick_size, closing_side),
                )
                prior_ticks = len(ticks)
                _wait_until(lambda: len(ticks) >= prior_ticks + 3)
                self.assertEqual(runtime.call(durable_evidence), before)

                runtime.close()
                runtime = SerializedPaperRuntime(factory)
                self.assertTrue(runtime.call(lambda owner: owner.robot_admission_ready()))
                runtime.start_robot_monitor()
                prior_ticks = len(ticks)
                _wait_until(lambda: len(ticks) >= prior_ticks + 3)
                self.assertEqual(runtime.call(durable_evidence), before)
                self.assertEqual(open_trade(), trade)
                self.assertEqual(len(protection_observations), 2)

                # Break one protection leg through the supported PAPER path.
                # A subsequent normal restart must fence admission instead of
                # trusting candidate.status == OPEN as proof of a healthy trade.
                deleted = runtime.call(lambda owner: owner.delete_take(
                    PaperStopDeleteRequest(
                        ClientActionId("acceptance-delete-take"), SYMBOL,
                    )
                ))
                self.assertEqual(deleted.status, CommandResultStatus.COMPLETED)
                runtime.close()
                runtime = SerializedPaperRuntime(factory)
                recovered = runtime.call(
                    lambda owner: owner.store.get_robot_runtime_state(ACCOUNT_ID)
                )
                self.assertFalse(runtime.call(lambda owner: owner.robot_admission_ready()))
                self.assertEqual(
                    (recovered.mode, recovered.recovery_status),
                    ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
                )
                self.assertIn("protection is incomplete", recovered.reason)
            finally:
                runtime.close()

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

                # Complete the real Robot PAPER lifecycle: cross TAKE through
                # the same ordered market-event path used by production coverage.
                take_price = protection.take_profit
                self.assertIsNotNone(take_price)
                tick = instrument.tick_size
                exit_bid = take_price + tick
                exit_ask = exit_bid + tick
                book.set(SYMBOL, bid=exit_bid, ask=exit_ask)
                crossing = _event_book(SYMBOL, bid=exit_bid, ask=exit_ask)
                runtime.call(
                    lambda owner: owner.process_robot_market_event(
                        SYMBOL, crossing, event_id="acceptance-take",
                        received_at_ms=crossing.received_at_ms,
                    )
                )

                def closed_trade():
                    current = runtime.call(
                        lambda owner: owner.store.get_robot_trade(trade.trade_id)
                    )
                    return current if current is not None and current.exit_time_ms is not None else None

                closed = _wait_until(closed_trade)
                self.assertEqual(closed.exit_reason, "TAKE")
                self.assertGreater(closed.realized_pnl_usdt, 0)
                final_position = runtime.call(
                    lambda owner: owner.store.get_position_projection(position_key)
                )
                self.assertEqual(final_position.side.value, "Flat")
                self.assertEqual(final_position.quantity.value, Decimal("0"))
            finally:
                runtime.close()


    def test_manual_position_is_never_adopted_as_robot_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database_path = root / "paper.sqlite3"
            candidate_dir = root / "candidates"
            instrument = _instrument()
            candles = _DeterministicCandleProvider()
            book = _MutableBookProvider()
            book.set(SYMBOL, bid=Decimal("99.9"), ask=Decimal("100"))

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
                manual = runtime.call(lambda owner: owner.market(MarketCommandRequest(
                    ClientActionId("manual-position-before-robot"),
                    SYMBOL,
                    OrderSide.BUY,
                    VolumeRequest(VolumeUnit.USDT, Decimal("20")),
                    Decimal("100"),
                    "Percent",
                    Decimal("1"),
                )))
                self.assertEqual(manual.status, CommandResultStatus.COMPLETED)
                baseline_executions = runtime.call(
                    lambda owner: owner.store.load_executions()
                )
                self.assertEqual(len(baseline_executions), 1)

                started = start_robot(database_path=database_path)
                self.assertEqual(
                    (started.mode, started.recovery_status),
                    ("ROBOT_RUNNING", "READY"),
                )
                create_signal_snapshot(
                    _snapshot(),
                    timeframe="1",
                    store_dir=candidate_dir,
                    candidate_id=CANDIDATE_ID,
                    created_at="2026-09-15T00:00:00+00:00",
                )
                admitted, created = admit_robot_candidate(
                    CANDIDATE_ID,
                    approval={"source": "foreign-position-acceptance"},
                    database_path=database_path,
                    store_dir=candidate_dir,
                )
                self.assertTrue(created)
                self.assertEqual(admitted.status, "APPROVED")
                runtime.start_robot_monitor()

                def candidate_record():
                    return runtime.call(
                        lambda owner: owner.store.get_robot_candidate(CANDIDATE_ID)
                    )

                _wait_until(lambda: (
                    candidate_record()
                    if (candidate_record().robot_state or {}).get("phase")
                    == robot_state_machine.PHASE_WAITING_BREAKOUT
                    else None
                ))
                candles.set(_candle(102, high=106, low=97, close=105))
                _wait_until(lambda: (
                    candidate_record()
                    if (candidate_record().robot_state or {}).get("phase")
                    == robot_state_machine.PHASE_WAITING_RETEST
                    else None
                ))
                candles.set(_candle(103, high=101, low=95, close=98))
                _wait_until(lambda: (
                    candidate_record()
                    if (candidate_record().robot_state or {}).get("phase")
                    == robot_state_machine.PHASE_RETEST_DETECTED
                    else None
                ))
                candles.set(_candle(104, high=99, low=97, close=98))

                invalidated = _wait_until(lambda: (
                    record if (record := candidate_record()).status == "INVALIDATED"
                    else None
                ))
                reason = invalidated.robot_state["execution"]["stopped_without_entry_reason"]
                self.assertIn("FOREIGN_POSITION_PRESENT_BEFORE_ROBOT_ENTRY", reason)
                self.assertIsNone(runtime.call(
                    lambda owner: owner.store.get_open_robot_trade_for_symbol(
                        ACCOUNT_ID, Symbol(SYMBOL),
                    )
                ))
                self.assertEqual(
                    runtime.call(lambda owner: owner.store.load_executions()),
                    baseline_executions,
                )
                self.assertEqual(
                    runtime.call(lambda owner: owner.store.load_active_paper_limits(
                        ACCOUNT_ID, Symbol(SYMBOL),
                    )),
                    (),
                )
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
