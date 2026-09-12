from decimal import Decimal
from pathlib import Path
import tempfile
import time
import unittest

import robot_partial_fill
import robot_state_machine
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.api.models import CommandResult, CommandResultStatus, PaperLimitMutationResult
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    Notional,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.persistence.sqlite_store import PositionProjectionUpdate, SQLiteStore


ACCOUNT_ID = TradingAccountId("paper")
SYMBOL = "TESTUSDT"
T0_MS = 1_800_000


def _snapshot(
    *,
    symbol=SYMBOL,
    pattern="Falling Wedge",
    apex_index=130,
    current_index=100,
    anchor_index=None,
    lower_touch_prices=(80.0, 82.0),
    upper_touch_prices=(150.0, 152.0),
    reference_price=100.0,
    start_width=20.0,
):
    anchor_index = current_index if anchor_index is None else anchor_index
    return {
        "symbol": symbol,
        "pattern": pattern,
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": current_index,
            "touches": {
                "lower_touch_points": (
                    [{"price": price, "counted": True} for price in lower_touch_prices]
                    + [{"price": 1.0, "counted": False}]
                ),
                "upper_touch_points": (
                    [{"price": price, "counted": True} for price in upper_touch_prices]
                    + [{"price": 999.0, "counted": False}]
                ),
            },
            "pair_metrics": {
                "reference_price": reference_price,
                "start_width": start_width,
            },
        },
        "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
            geometry_index=anchor_index,
            source_candle_time_ms=T0_MS,
            timeframe="1",
        ),
    }


def _candle_at(index, *, high, low, close):
    return {
        "time_ms": T0_MS + (index - 100) * 60_000,
        "high": high,
        "low": low,
        "close": close,
    }


class _ScriptedCandleFeed:
    """Fake pull-based closed-candle provider: a per-symbol FIFO queue."""

    def __init__(self):
        self._queues: dict[str, list[dict]] = {}
        self.calls: list[str] = []

    def push(self, symbol, candle):
        self._queues.setdefault(symbol, []).append(candle)

    def __call__(self, symbol):
        self.calls.append(symbol)
        queue = self._queues.get(symbol)
        if not queue:
            return None
        return queue.pop(0)


class _FakeActionExecutor:
    """Records every submission and simulates fills directly against the
    store (1 WV == 1 unit of quantity), bypassing the real pretrade
    guard/execution engine -- that pipeline has its own dedicated coverage
    in tests/test_terminal_persistence.py and tests/test_terminal_execution_engine.py.
    This fake exists to test RobotBreakoutMonitor's orchestration only.
    """

    def __init__(self, store, account_id, clock):
        self.store = store
        self.account_id = account_id
        self.clock = clock
        self.limit_calls: list = []
        self.cancel_calls: list = []
        self.market_calls: list = []
        self.protection_calls: list[tuple[str, object]] = []
        self._exec_counter = 0
        self._order_counter = 0
        self.fail_create_limit = False

    def create_limit(self, request):
        if self.fail_create_limit:
            raise RuntimeError("boom: simulated execution failure")
        self.limit_calls.append(request)
        self._order_counter += 1
        order_id = OrderId(f"test-limit-{self._order_counter}")
        self.store.create_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=f"fp-{self._order_counter}",
            order_id=order_id,
            order_link_id=f"link-{self._order_counter}",
            trading_account_id=self.account_id,
            symbol=Symbol(request.symbol),
            side=request.side,
            price=request.limit_price,
            quantity=request.volume.amount,
            created_at_ms=self.clock(),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "created", order_id.value,
        )

    def cancel_limit(self, request):
        self.cancel_calls.append(request)
        order, changed = self.store.cancel_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=f"cancel-fp-{request.order_id}",
            order_id=OrderId(request.order_id),
            trading_account_id=self.account_id,
            updated_at_ms=self.clock(),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED,
            "cancelled" if changed else "already_absent", request.order_id,
        )

    def market(self, request):
        self.market_calls.append(request)
        self._apply_fill(
            request.symbol, request.side, request.volume.amount,
            request.sizing_reference_price,
            order_id=OrderId(f"test-market-{len(self.market_calls)}"),
        )
        return CommandResult(
            request.client_action_id.value, CommandResultStatus.COMPLETED, "filled", "market filled",
        )

    def create_stop(self, request):
        self.protection_calls.append(("create_stop", request))
        return None

    def amend_stop(self, request):
        self.protection_calls.append(("amend_stop", request))
        return None

    def create_take(self, request):
        self.protection_calls.append(("create_take", request))
        return None

    def amend_take(self, request):
        self.protection_calls.append(("amend_take", request))
        return None

    def full_close(self, request):
        self.protection_calls.append(("full_close", request))
        return None

    def fill_resting_limit(self, order_id_str, symbol, side, quantity, price):
        self._apply_fill(symbol, side, quantity, price, order_id=OrderId(order_id_str), resting=True)

    def _apply_fill(self, symbol, side, quantity, price, *, order_id, resting=False):
        self._exec_counter += 1
        key = PositionKey(self.account_id, Category.LINEAR, Symbol(symbol), 0)
        existing = self.store.get_position_projection(key)
        prior_quantity = existing.quantity.value if existing else Decimal("0")
        prior_notional = (
            existing.quantity.value * existing.average_entry.value
            if existing and existing.average_entry else Decimal("0")
        )
        new_quantity = prior_quantity + quantity
        new_average = (prior_notional + quantity * price) / new_quantity
        execution = Execution(
            dedup_key=ExecutionDedupKey(
                self.account_id, Category.LINEAR, ExecutionId(f"exec-{self._exec_counter}"),
            ),
            order_id=order_id, symbol=Symbol(symbol), side=side,
            price=Price(price), quantity=Quantity(quantity), fee=Decimal("0"),
            exchange_timestamp_ms=self.clock(),
        )
        projection = PositionProjectionUpdate(
            position_key=key,
            side=PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT,
            quantity=Quantity(new_quantity), average_entry=Price(new_average),
            realized_pnl=Decimal("0"), accumulated_fee=Decimal("0"),
            engaged_notional=Notional(new_quantity * new_average),
            sync_state="synced",
            expected_version=existing.version if existing else None,
            updated_at_ms=self.clock(),
        )
        if resting:
            self.store.apply_paper_limit_execution_once(
                order_id, execution, projection, updated_at_ms=self.clock(),
            )
        else:
            self.store.apply_execution_once(execution, projection)


class _Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        self.value += 1
        return self.value

    def advance(self, delta_ms):
        self.value += delta_ms


class RobotBreakoutMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "terminal.db"
        self.store = SQLiteStore.open(self.db_path)
        self.feed = _ScriptedCandleFeed()
        self.clock = _Clock()
        self.executor = _FakeActionExecutor(self.store, ACCOUNT_ID, self.clock)
        self.monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            action_executor=self.executor,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
        )

    def tearDown(self):
        # tick() runs synchronously on this (the test) thread throughout, so
        # the monitor's own lazily-opened connection was cached on this same
        # thread -- close it before the temp directory cleanup, or an
        # unclosed sqlite3 connection can keep the file locked on Windows.
        self.monitor.close()
        self.store.close()
        self.temp_dir.cleanup()

    def _create_candidate(self, candidate_id="candidate-1", *, symbol=SYMBOL, **snapshot_kwargs):
        candidate, created = self.store.create_robot_candidate(
            candidate_id=candidate_id,
            trading_account_id=ACCOUNT_ID,
            symbol=Symbol(symbol),
            status="APPROVED",
            signal_snapshot=_snapshot(symbol=symbol, **snapshot_kwargs),
            approved_at_ms=1,
            updated_at_ms=1,
        )
        self.assertTrue(created)
        return candidate

    def _drive_to_retest_detected(self, candidate_id="candidate-1", *, push_followup_candle=True):
        """Init, breakout, retest -- reaches RETEST_DETECTED (no LIMIT submitted yet)."""
        self.monitor.tick()  # initialize
        self.feed.push(SYMBOL, _candle_at(101, high=96, low=94, close=95))
        self.monitor.tick()  # NO_TRANSITION
        self.feed.push(SYMBOL, _candle_at(102, high=106, low=97, close=105))
        self.monitor.tick()  # BREAKOUT -> WAITING_RETEST
        self.feed.push(SYMBOL, _candle_at(103, high=101, low=95, close=98))
        self.monitor.tick()  # RETEST -> RETEST_DETECTED
        record = self.store.get_robot_candidate(candidate_id)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)
        if push_followup_candle:
            # RETEST_DETECTED's first-entry freshness gate reads one more
            # closed candle (well before the default apex_index=130) before
            # it will submit the initial LIMIT on the next tick.
            self.feed.push(SYMBOL, _candle_at(104, high=99, low=97, close=98))
        return record

    def test_lazily_initializes_missing_robot_state_without_reading_a_candle(self):
        self._create_candidate()

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.feed.calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)

    def test_retest_detected_submits_limit_on_the_next_tick(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.assertEqual(self.executor.limit_calls, [])

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.limit_calls), 1)
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["execution"]["limit_order_id"], "test-limit-1")

    def test_advance_failure_records_execution_error_diagnostics(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.executor.fail_create_limit = True

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())
        record = self.store.get_robot_candidate("candidate-1")
        execution = record.robot_state["execution"]
        self.assertIn("boom: simulated execution failure", execution["last_execution_error"])
        self.assertEqual(execution["attempt_count"], 1)
        self.assertIsInstance(execution["last_attempt_at_ms"], int)
        self.assertGreater(execution["last_attempt_at_ms"], 0)

        # A second consecutive failure increments rather than resets the count
        # (each attempt consumes one fresh closed candle for the RETEST_DETECTED
        # freshness gate before reaching create_limit()).
        self.feed.push(SYMBOL, _candle_at(105, high=99, low=97, close=98))
        self.monitor.tick()
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["execution"]["attempt_count"], 2)

        # Recovery still works once the underlying failure clears.
        self.executor.fail_create_limit = False
        self.feed.push(SYMBOL, _candle_at(106, high=99, low=97, close=98))
        advanced = self.monitor.tick()
        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.limit_calls), 1)

    # -- RETEST_DETECTED first-entry freshness gate (fail-closed on staleness) --
    #
    # robot_state_machine.process_closed_candle()/resume_without_replay() both
    # treat RETEST_DETECTED as terminal (_TERMINAL_PHASES), so nothing else
    # re-validates the frozen apex once retest is detected. These tests cover
    # the gate _advance_retest_detected() now runs, once, immediately before
    # the very first entry order for a candidate.

    def test_a_current_index_before_apex_allows_initial_limit_submission(self):
        self._create_candidate(apex_index=130)  # default; well past retest_index=103
        self._drive_to_retest_detected(push_followup_candle=False)
        self.feed.push(SYMBOL, _candle_at(104, high=99, low=97, close=98))

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.limit_calls), 1)
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)
        self.assertEqual(record.robot_state["execution"]["limit_order_id"], "test-limit-1")

    def test_b_current_index_equal_to_apex_expires_without_submitting(self):
        self._create_candidate(apex_index=104)
        self._drive_to_retest_detected(push_followup_candle=False)
        self.feed.push(SYMBOL, _candle_at(104, high=99, low=97, close=98))

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "EXPIRED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)
        self.assertEqual(record.robot_state["geometry_cursor"], 104)

        # Terminal: a later tick never revisits or resubmits.
        self.feed.push(SYMBOL, _candle_at(105, high=99, low=97, close=98))
        self.assertEqual(self.monitor.tick(), ())
        self.assertEqual(self.executor.limit_calls, [])

    def test_c_current_index_past_apex_expires_without_submitting(self):
        self._create_candidate(apex_index=104)
        self._drive_to_retest_detected(push_followup_candle=False)
        self.feed.push(SYMBOL, _candle_at(110, high=99, low=97, close=98))

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "EXPIRED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)

    def test_d_unavailable_or_invalid_candle_fails_closed_without_submitting(self):
        self._create_candidate(apex_index=130)
        self._drive_to_retest_detected(push_followup_candle=False)

        # No candle queued at all.
        advanced = self.monitor.tick()
        self.assertEqual(advanced, ())
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)

        # A candle whose timestamp cannot project into the frozen index space
        # (misaligned to the 1m grid) must also fail closed, not raise/crash.
        self.feed.push(SYMBOL, {
            "time_ms": T0_MS + 30_000, "high": 99, "low": 97, "close": 98,
        })
        advanced = self.monitor.tick()
        self.assertEqual(advanced, ())
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)

    def test_e_restart_with_stale_retest_detected_and_no_limit_order_id_expires_not_revives(self):
        """Simulates a process restart finding a durable RETEST_DETECTED
        candidate (no execution/limit_order_id) whose frozen apex has already
        passed while the process was down -- must expire on the first tick of
        the NEW monitor instance, never submit."""

        candidate, created = self.store.create_robot_candidate(
            candidate_id="candidate-1",
            trading_account_id=ACCOUNT_ID,
            symbol=Symbol(SYMBOL),
            status="APPROVED",
            signal_snapshot=_snapshot(apex_index=104, current_index=100),
            approved_at_ms=1,
            updated_at_ms=1,
        )
        self.assertTrue(created)
        self.store.save_robot_candidate_state(
            "candidate-1", status="APPROVED",
            robot_state={
                "state_version": robot_state_machine.STATE_VERSION,
                "phase": robot_state_machine.PHASE_RETEST_DETECTED,
                "pattern": "Falling Wedge",
                "direction": robot_state_machine.DIRECTION_LONG,
                "geometry_cursor": 103,
                "breakout_index": 102,
                "retest_index": 103,
                "last_event": robot_state_machine.EVENT_RETEST,
            },
            expected_revision=0, updated_at_ms=1,
        )
        self.feed.push(SYMBOL, _candle_at(110, high=99, low=97, close=98))

        # A brand-new monitor instance -- nothing carried over in memory.
        restarted = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            action_executor=self.executor,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
        )
        try:
            advanced = restarted.tick()
        finally:
            restarted.close()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "EXPIRED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)

    def test_match_resting_orders_is_invoked_with_the_candidate_symbol(self):
        match_calls: list[str] = []
        # tearDown() closes self.monitor unconditionally -- swap it for a
        # second monitor over the same store rather than leaving two live
        # monitor objects for this one test.
        self.monitor.close()
        self.monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            action_executor=self.executor,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
            match_resting_orders=match_calls.append,
        )
        self._create_candidate()
        self._drive_to_retest_detected()
        self.assertEqual(match_calls, [])

        self.monitor.tick()  # submits the initial LIMIT; no resting order to match yet
        self.assertEqual(match_calls, [])

        self.monitor.tick()  # polls the now-resting LIMIT: matches first
        self.assertEqual(match_calls, [SYMBOL])

    def test_candidate_expires_at_apex_without_submitting_a_limit(self):
        self._create_candidate(apex_index=100, current_index=100)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "EXPIRED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)
        self.assertEqual(self.executor.limit_calls, [])

        self.monitor.tick()
        self.assertEqual(self.feed.calls, [])

    def test_full_limit_fill_creates_protected_trade(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]

        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_path, "LIMIT")
        self.assertEqual(trade.actual_wv, Decimal("1"))
        self.assertEqual(trade.average_entry, Decimal("81"))
        # structural_extreme = min(counted lower_touch_points) = 80.0; tick=0.1
        # -> candidate stop = 79.9; distance (81-79.9)/81 = 0.0136 <= 2% -> structural, not fallback.
        self.assertEqual(trade.stop_price, Decimal("79.9"))
        # reference=100, start_width=20 -> target=120 (Falling Wedge/LONG -> UP); take = 100 + 20*0.9 = 118.
        self.assertEqual(trade.take_price, Decimal("118"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )

        # Once OPEN, the outer tick() loop skips this candidate entirely.
        self.monitor.tick()
        self.assertEqual(len(self.executor.protection_calls), 2)

    def test_partial_fill_waits_then_completes_via_market_and_creates_mixed_trade(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]

        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"))
        self.feed.push(SYMBOL, _candle_at(104, high=82, low=80, close=81))
        self.monitor.tick()  # observes the partial fill -> cancels remainder, WAIT (timer not elapsed)

        self.assertEqual(len(self.executor.cancel_calls), 1)
        order = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["execution"]["stop_price"], "79.9")

        self.clock.advance(robot_partial_fill.PARTIAL_COMPLETION_WAIT_MS + 1000)
        self.feed.push(SYMBOL, _candle_at(105, high=82, low=80.5, close=81))
        advanced = self.monitor.tick()  # elapsed, adverse move tiny, rr fine -> MARKET_COMPLETE

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.market_calls), 1)
        market_request = self.executor.market_calls[0]
        self.assertAlmostEqual(market_request.volume.amount, Decimal("0.4"))

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_path, "MIXED")
        self.assertEqual(trade.actual_wv, Decimal("1"))

    def test_unavailable_candle_leaves_state_untouched_and_does_not_crash(self):
        self._create_candidate()
        self.monitor.tick()  # initialize

        advanced = self.monitor.tick()  # feed has nothing queued -> None

        self.assertEqual(advanced, ())
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)

    def test_concurrent_writer_is_absorbed_without_raising(self):
        record = self._create_candidate()
        state, _event = robot_state_machine.initialize_state({
            "candidate_id": record.candidate_id,
            "status": "APPROVED",
            "timeframe": "1",
            "signal_snapshot": record.signal_snapshot,
        })
        # Simulate another writer (e.g. RobotRecoveryCoordinator) already
        # having advanced this candidate's revision past what this stale
        # in-memory record reflects.
        self.store.save_robot_candidate_state(
            record.candidate_id, status="APPROVED", robot_state=state,
            expected_revision=record.state_revision, updated_at_ms=2,
        )

        # _persist_state must swallow ConcurrentUpdate rather than raise.
        self.monitor._persist_state(record, state)

        current = self.store.get_robot_candidate(record.candidate_id)
        self.assertEqual(current.state_revision, 1)

    def test_two_candidates_on_different_symbols_are_independent(self):
        self._create_candidate("candidate-a", symbol=SYMBOL)
        self._create_candidate("candidate-b", symbol="OTHERUSDT")
        self.monitor.tick()  # initializes both

        self.feed.push(SYMBOL, _candle_at(101, high=106, low=97, close=105))
        # candidate-b's symbol gets no queued candle this tick -> unaffected.
        advanced = self.monitor.tick()

        self.assertEqual(set(advanced), {"candidate-a"})
        a = self.store.get_robot_candidate("candidate-a")
        b = self.store.get_robot_candidate("candidate-b")
        self.assertEqual(a.robot_state["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertEqual(b.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
        self.assertIn("OTHERUSDT", self.feed.calls)

    def test_start_and_close_do_not_tick_within_the_interval(self):
        monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            action_executor=self.executor,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
            tick_interval_s=60.0,
        )
        self._create_candidate()
        monitor.start()
        monitor.close()

        # The background thread must never tick before a full interval
        # elapses, so a short-lived caller (every existing test included)
        # never reaches a real market-data call.
        self.assertEqual(self.feed.calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertIsNone(record.robot_state)

    def test_structural_extreme_and_frozen_prices_for_short(self):
        from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor as M

        snapshot = _snapshot(pattern="Rising Wedge")
        extreme = M._structural_extreme(snapshot, robot_state_machine.DIRECTION_SHORT)
        self.assertEqual(extreme, Decimal("152"))  # max of counted upper_touch_points
        reference, target = M._frozen_prices(snapshot, robot_state_machine.DIRECTION_SHORT)
        self.assertEqual(reference, Decimal("100"))
        self.assertEqual(target, Decimal("80"))  # reference - start_width (DOWN)


class RobotBreakoutMonitorRealThreadTests(unittest.TestCase):
    """Post-closure regression test for the CR-ROBOT-BREAKOUT-MONITOR-001
    SQLiteStore thread-ownership bug (see DOCUMENTS/ROBOT_RUN_INDEX.md): the
    monitor previously accepted a SQLiteStore opened by the constructing
    thread and used it from its own background thread, which
    SQLiteStore._assert_owner() rejects on every real call. Every other test
    in this module calls .tick() synchronously and would not have caught
    this -- this test drives the real background thread through an actual
    tick interval instead.
    """

    def test_real_background_thread_ticks_using_its_own_store_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "terminal.db"
            setup_store = SQLiteStore.open(db_path)
            try:
                setup_store.create_robot_candidate(
                    candidate_id="candidate-thread",
                    trading_account_id=ACCOUNT_ID,
                    symbol=Symbol(SYMBOL),
                    status="APPROVED",
                    signal_snapshot=_snapshot(),
                    approved_at_ms=1,
                    updated_at_ms=1,
                )
            finally:
                setup_store.close()

            monitor = RobotBreakoutMonitor(
                lambda: SQLiteStore.open(db_path),
                ACCOUNT_ID,
                get_closed_candle=_ScriptedCandleFeed(),
                action_executor=_FakeActionExecutor(None, ACCOUNT_ID, _Clock()),
                tick_size_provider=lambda symbol: Decimal("0.1"),
                clock_ms=lambda: int(time.time() * 1000),
                tick_interval_s=0.05,
            )
            monitor.start()
            try:
                deadline = time.monotonic() + 5.0
                record = None
                while time.monotonic() < deadline:
                    time.sleep(0.05)
                    verify_store = SQLiteStore.open(db_path)
                    try:
                        record = verify_store.get_robot_candidate("candidate-thread")
                    finally:
                        verify_store.close()
                    if record.robot_state is not None:
                        break
            finally:
                monitor.close()

            self.assertIsNotNone(record)
            self.assertIsNotNone(
                record.robot_state,
                "the real background thread never advanced the candidate -- "
                "this is exactly the SQLiteStore thread-ownership regression",
            )
            self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
            self.assertGreaterEqual(record.state_revision, 1)


if __name__ == "__main__":
    unittest.main()
