from contextlib import redirect_stdout
import os
from decimal import Decimal
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch

import robot_protection
import robot_state_machine
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.api.models import (
    ClientActionId, CommandResult, CommandResultStatus, PaperLimitCancelRequest,
    PaperLimitMutationResult, PaperStopMutationResult,
)
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
        self.amend_calls: list = []
        self.cancel_calls: list = []
        self.market_calls: list = []
        self.protection_calls: list[tuple[str, object]] = []
        self._exec_counter = 0
        self._order_counter = 0
        self.fail_create_limit = False
        self.fail_create_stop = False
        # A real PaperRuntime.full_close() both completes and actually
        # flattens the authoritative position; these two knobs let tests
        # independently simulate an incomplete/rejected close (status) and a
        # completed-but-still-non-flat close (flattens), matching the two
        # distinct "do not terminalize prematurely" scenarios.
        self.full_close_status = CommandResultStatus.COMPLETED
        self.full_close_flattens = True

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

    def amend_limit(self, request):
        self.amend_calls.append(request)
        order, changed = self.store.amend_paper_limit(
            client_action_id=request.client_action_id.value,
            request_fingerprint=(
                f"amend-fp-{request.order_id}-{request.limit_price}"
            ),
            order_id=OrderId(request.order_id),
            trading_account_id=self.account_id,
            price=request.limit_price,
            updated_at_ms=self.clock(),
        )
        return PaperLimitMutationResult(
            request.client_action_id.value,
            CommandResultStatus.COMPLETED,
            "amended" if changed else "duplicate_action",
            order.order_id.value,
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
        if self.fail_create_stop:
            raise RuntimeError("boom: simulated protection submission failure")
        self.protection_calls.append(("create_stop", request))
        return PaperStopMutationResult(request.client_action_id.value, CommandResultStatus.COMPLETED, "created")

    def amend_stop(self, request):
        self.protection_calls.append(("amend_stop", request))
        return None

    def create_take(self, request):
        self.protection_calls.append(("create_take", request))
        return PaperStopMutationResult(request.client_action_id.value, CommandResultStatus.COMPLETED, "created")

    def amend_take(self, request):
        self.protection_calls.append(("amend_take", request))
        return None

    def full_close(self, request):
        self.protection_calls.append(("full_close", request))
        if self.full_close_status == CommandResultStatus.COMPLETED and self.full_close_flattens:
            self._flatten(request.symbol)
        return CommandResult(
            request.client_action_id.value, self.full_close_status, "closed", "full close",
        )

    def fill_resting_limit(self, order_id_str, symbol, side, quantity, price):
        self._apply_fill(symbol, side, quantity, price, order_id=OrderId(order_id_str), resting=True)

    def _flatten(self, symbol):
        key = PositionKey(self.account_id, Category.LINEAR, Symbol(symbol), 0)
        current = self.store.get_position_projection(key)
        if current is None or current.quantity.value <= 0:
            return
        self._exec_counter += 1
        self.store.apply_execution_once(
            Execution(
                dedup_key=ExecutionDedupKey(
                    self.account_id, Category.LINEAR, ExecutionId(f"exec-close-{self._exec_counter}"),
                ),
                order_id=OrderId(f"test-full-close-{self._exec_counter}"), symbol=Symbol(symbol),
                side=OrderSide.SELL, price=current.average_entry, quantity=current.quantity,
                fee=Decimal("0"), exchange_timestamp_ms=self.clock(),
            ),
            PositionProjectionUpdate(
                position_key=key, side=PositionSide.FLAT, quantity=Quantity(Decimal("0")),
                average_entry=None, realized_pnl=current.realized_pnl,
                accumulated_fee=current.accumulated_fee, engaged_notional=Notional(Decimal("0")),
                sync_state="synced", expected_version=current.version, updated_at_ms=self.clock(),
            ),
        )

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
        # Default admission state for every pre-existing test in this module:
        # (ROBOT_RUNNING, READY), matching what RobotRecoveryCoordinator.recover()
        # would have already established before RobotBreakoutMonitor ever ticks
        # in production. Tests covering the PAUSE/STOP/RECONCILIATION_REQUIRED
        # admission gate override this explicitly via
        # self.store.update_robot_runtime_state(...).
        self.store.initialize_robot_runtime_state(ACCOUNT_ID, updated_at_ms=1)
        self.store.update_robot_runtime_state(
            ACCOUNT_ID, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=1, updated_at_ms=1,
        )
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

    def test_unsupported_pattern_without_state_is_invalidated_once_and_unblocks_recovery(self):
        from contextlib import redirect_stdout
        import io

        from terminal.application.robot_recovery import RobotRecoveryCoordinator

        self._create_candidate(pattern="Triangle Compression")

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(self.monitor.tick(), ("candidate-1",))
            self.assertEqual(self.monitor.tick(), ())

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(record.robot_state["phase"], "INVALIDATED_UNSUPPORTED_PATTERN")
        self.assertEqual(record.robot_state["pattern"], "Triangle Compression")
        self.assertIn("unsupported Robot v0.1 pattern", record.robot_state["invalidated_reason"])
        self.assertEqual(output.getvalue().count("[ROBOT CANDIDATE INVALIDATED]"), 1)
        self.assertNotIn("[ROBOT CANDIDATE ERROR]", output.getvalue())

        # reconcile_restart only sees APPROVED candidates: recovery no longer fails.
        result = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID,
            latest_geometry_index_provider=lambda candidate_id, snapshot: 100,
            clock_ms=self.clock,
        ).recover()
        self.assertEqual(result.runtime_state.recovery_status, "READY")
        self.assertEqual(result.decisions, ())

    def test_supported_pattern_state_error_is_not_invalidated(self):
        self._create_candidate(apex_index="broken")

        self.assertEqual(self.monitor.tick(), ())

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertIsNone(record.robot_state)

    def _seed_finished_history(self, count):
        """``count`` CLOSED/EXPIRED/INVALIDATED candidates on other symbols."""
        for index in range(count):
            candidate_id = f"finished-{index}"
            symbol = f"OLD{index}USDT"
            self.store.create_robot_candidate(
                candidate_id=candidate_id, trading_account_id=ACCOUNT_ID, symbol=Symbol(symbol),
                status="APPROVED", signal_snapshot=_snapshot(symbol=symbol),
                approved_at_ms=1, updated_at_ms=1,
            )
            kind = index % 3
            if kind == 0:
                self.store.create_robot_trade(
                    trade_id=f"trade-{candidate_id}", trading_account_id=ACCOUNT_ID,
                    candidate_id=candidate_id, symbol=Symbol(symbol), direction="LONG",
                    pattern="Falling Wedge", source_timeframe="1", signal_time_ms=1,
                    entry_time_ms=2, entry_path="LIMIT", actual_wv=Decimal("1"),
                    average_entry=Decimal("100"), stop_price=Decimal("90"),
                    take_price=Decimal("120"), entry_quantity=Decimal("1"),
                    entry_position_version=1, created_at_ms=2,
                )
                self.store.close_robot_trade(
                    f"trade-{candidate_id}", exit_time_ms=3, exit_price=Decimal("120"),
                    exit_reason="TAKE", realized_pnl_usdt=Decimal("20"),
                    realized_pnl_pct=Decimal("20"), fees_costs_usdt=Decimal("0"),
                    updated_at_ms=3,
                )
            else:
                self.store.save_robot_candidate_state(
                    candidate_id, status=("EXPIRED", "INVALIDATED")[kind - 1],
                    robot_state={"phase": "EXPIRED_AT_APEX"}, expected_revision=0,
                    updated_at_ms=2,
                )

    def test_tick_does_not_read_finished_candidates(self):
        self._create_candidate()
        self._seed_finished_history(100)
        statuses = {r.status for r in self.store.load_robot_candidates(ACCOUNT_ID)}
        self.assertEqual(statuses, {"APPROVED", "CLOSED", "EXPIRED", "INVALIDATED"})
        # Corrupt every finished snapshot: parsing any of them would now raise.
        self.store._connection.execute(
            "UPDATE robot_candidates SET signal_snapshot_json='not json' WHERE status!='APPROVED'"
        )
        with self.assertRaises(Exception):
            self.store.load_robot_candidates(ACCOUNT_ID)

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(self.monitor.tick(), ("candidate-1",))
        self.assertNotIn("ERROR", output.getvalue())
        self.assertIsNotNone(self.store.get_robot_candidate("candidate-1").robot_state)

    def test_load_robot_candidates_by_status_matches_full_read(self):
        self._create_candidate("candidate-1")
        self._create_candidate("candidate-2", symbol="OTHERUSDT")
        self._seed_finished_history(6)
        full = self.store.load_robot_candidates(ACCOUNT_ID)
        for statuses in (("APPROVED",), ("CLOSED", "EXPIRED"), ("OPEN",), ("INVALIDATED", "APPROVED")):
            with self.subTest(statuses=statuses):
                self.assertEqual(
                    self.store.load_robot_candidates_by_status(ACCOUNT_ID, statuses),
                    tuple(record for record in full if record.status in statuses),
                )
        with self.assertRaises(ValueError):
            self.store.load_robot_candidates_by_status(ACCOUNT_ID, ())
        with self.assertRaises(ValueError):
            self.store.load_robot_candidates_by_status(ACCOUNT_ID, ("DONE",))

    # --- retest LIMIT take/stop filter (MIN_ENTRY_RR) -------------------------------------

    def _rr_check(self, direction, *, reference, extreme, entry="1000", env=None):
        """Call the pre-placement filter directly with a planned entry of ``entry``.

        Snapshot geometry gives stop = extreme -/+ 0.1 (1% from entry 1000) and
        take = reference +/- 0.9 * 10, so ``reference`` picks the ratio.
        """
        long_side = direction == "LONG"
        snapshot = _snapshot(
            pattern="Falling Wedge" if long_side else "Rising Wedge",
            lower_touch_prices=(extreme,) if long_side else (1.0,),
            upper_touch_prices=(1.0,) if long_side else (extreme,),
            reference_price=reference, start_width=10.0,
        )
        record = SimpleNamespace(
            candidate_id="candidate-rr", symbol=Symbol(SYMBOL), signal_snapshot=snapshot,
        )
        plan = SimpleNamespace(
            direction=direction, request=SimpleNamespace(limit_price=Decimal(entry)),
        )
        environment = {"ROBOT_MIN_ENTRY_RR": env} if env is not None else {}
        with patch.dict(os.environ, environment):
            if env is None:
                os.environ.pop("ROBOT_MIN_ENTRY_RR", None)
            with redirect_stdout(io.StringIO()):
                return self.monitor._entry_rr_skip(record, plan)

    def test_entry_rr_below_threshold_is_skipped_for_long_and_short(self):
        # LONG: entry 1000, stop 990 (1% risk), take = reference + 9 -> rr = reward% / 1%.
        long_skip = self._rr_check("LONG", reference=1005.0, extreme=990.1)  # take 1014 -> 1.4
        self.assertEqual(long_skip[0], "SKIPPED_POOR_RR")
        self.assertEqual(
            {key: Decimal(value) for key, value in long_skip[1].items()},
            {
                "entry_price": Decimal("1000"), "min_rr": Decimal("1.5"),
                "stop_price": Decimal("990"), "take_price": Decimal("1014"), "rr": Decimal("1.4"),
            },
        )
        # SHORT: entry 1000, stop 1010, take = reference - 9 -> 986 -> 1.4
        short_skip = self._rr_check("SHORT", reference=995.0, extreme=1009.9)
        self.assertEqual(short_skip[0], "SKIPPED_POOR_RR")
        self.assertEqual(
            tuple(Decimal(short_skip[1][key]) for key in ("stop_price", "take_price", "rr")),
            (Decimal("1010"), Decimal("986"), Decimal("1.4")),
        )

    def test_entry_rr_at_or_above_threshold_is_not_skipped(self):
        for direction, extreme, references in (
            ("LONG", 990.1, (1006.0, 1011.0)),   # take 1015 -> rr 1.5, take 1020 -> rr 2.0
            ("SHORT", 1009.9, (994.0, 989.0)),   # take 985 -> rr 1.5, take 980 -> rr 2.0
        ):
            for reference in references:
                with self.subTest(direction=direction, reference=reference):
                    self.assertIsNone(
                        self._rr_check(direction, reference=reference, extreme=extreme)
                    )

    def test_entry_rr_threshold_follows_environment_variable(self):
        # rr is 1.5 here: passes by default, skipped when the threshold is raised.
        self.assertIsNone(self._rr_check("LONG", reference=1006.0, extreme=990.1))
        raised = self._rr_check("LONG", reference=1006.0, extreme=990.1, env="1.6")
        self.assertEqual(raised[0], "SKIPPED_POOR_RR")
        self.assertEqual((Decimal(raised[1]["min_rr"]), Decimal(raised[1]["rr"])), (Decimal("1.6"), Decimal("1.5")))
        # rr 1.4 passes when the threshold is lowered.
        self.assertIsNone(self._rr_check("LONG", reference=1005.0, extreme=990.1, env="1.4"))
        # Invalid values fall back to the default 1.5.
        for bad in ("abc", "-1", "11", "NaN", ""):
            with self.subTest(env=bad):
                skipped = self._rr_check("LONG", reference=1005.0, extreme=990.1, env=bad)
                self.assertEqual(Decimal(skipped[1]["min_rr"]), Decimal("1.5"))

    def test_entry_rr_unavailable_places_the_limit_as_before(self):
        # Target on the wrong side of the reference: no take can be computed.
        snapshot = _snapshot(reference_price=100.0, start_width=0.0)
        record = SimpleNamespace(
            candidate_id="candidate-rr", symbol=Symbol(SYMBOL), signal_snapshot=snapshot,
        )
        plan = SimpleNamespace(direction="LONG", request=SimpleNamespace(limit_price=Decimal("100")))
        with redirect_stdout(io.StringIO()) as output:
            self.assertIsNone(self.monitor._entry_rr_skip(record, plan))
        self.assertIn("[ROBOT ENTRY RR UNAVAILABLE]", output.getvalue())

    def test_poor_rr_candidate_places_no_limit_and_is_terminated_with_reason(self):
        # start_width=1 keeps the frozen take close: rr is about 1.9 (default fixture is above 10).
        self._create_candidate(start_width=1.0)
        self._drive_to_retest_detected()
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "10"}), \
                redirect_stdout(io.StringIO()):
            self.monitor.tick()

        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        execution = record.robot_state["execution"]
        self.assertNotIn("limit_order_id", execution)
        self.assertEqual(execution["stopped_without_entry_reason"], "SKIPPED_POOR_RR")
        details = execution["entry_rr_filter"]
        self.assertEqual(details["min_rr"], "10")
        self.assertEqual(
            sorted(details), ["entry_price", "min_rr", "rr", "stop_price", "take_price"],
        )
        self.assertLess(Decimal(details["rr"]), Decimal("10"))

    def test_rr_equal_to_threshold_still_places_the_limit(self):
        self._create_candidate(start_width=1.0)
        record = self._drive_to_retest_detected()
        plan = self.monitor._build_initial_retest_limit_plan(record, record.robot_state)
        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": "10"}), redirect_stdout(io.StringIO()):
            rr = self.monitor._entry_rr_skip(record, plan)[1]["rr"]

        with patch.dict(os.environ, {"ROBOT_MIN_ENTRY_RR": rr}):
            self.monitor.tick()

        self.assertEqual(len(self.executor.limit_calls), 1)
        execution = self.store.get_robot_candidate("candidate-1").robot_state["execution"]
        self.assertIn("limit_order_id", execution)
        self.assertNotIn("entry_rr_filter", execution)

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

    def test_unfilled_entry_limit_reprices_same_order_after_five_closed_candles(self):
        self._create_candidate(apex_index=130)
        self._drive_to_retest_detected()
        self.monitor.tick()  # initial LIMIT; freshness index=104
        record = self.store.get_robot_candidate("candidate-1")
        order_id = record.robot_state["execution"]["limit_order_id"]
        initial_order = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(record.robot_state["execution"]["last_limit_index"], 104)

        self.feed.push(SYMBOL, _candle_at(108, high=99, low=97, close=98))
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())
        self.assertEqual(self.executor.amend_calls, [])
        self.assertEqual(
            self.store.get_paper_limit(order_id, ACCOUNT_ID).price,
            initial_order.price,
        )

        self.feed.push(SYMBOL, _candle_at(109, high=99, low=90, close=92))
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.amend_calls), 1)
        amend = self.executor.amend_calls[0]
        self.assertEqual(amend.order_id, order_id)
        self.assertEqual(amend.limit_price, Decimal("91.2"))
        amended = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(amended.order_id.value, order_id)
        self.assertEqual(amended.price, Decimal("91.2"))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["execution"]["last_limit_index"], 109)
        self.assertEqual(len(self.executor.limit_calls), 1)

    def test_unfilled_entry_limit_cancels_and_expires_at_apex(self):
        self._create_candidate(apex_index=110)
        self._drive_to_retest_detected()
        self.monitor.tick()  # initial LIMIT at freshness index=104
        record = self.store.get_robot_candidate("candidate-1")
        order_id = record.robot_state["execution"]["limit_order_id"]

        self.feed.push(SYMBOL, _candle_at(110, high=95, low=89, close=91))
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.cancel_calls[0].order_id, order_id)
        order = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(order.status, "cancelled")
        expired = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(expired.status, "EXPIRED")
        self.assertEqual(
            expired.robot_state["phase"],
            robot_state_machine.PHASE_EXPIRED_AT_APEX,
        )
        self.assertEqual(
            expired.robot_state["execution"]["cancelled_at_apex_index"],
            110,
        )

    def test_inactive_zero_fill_entry_limit_invalidates_instead_of_hanging(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        record = self.store.get_robot_candidate("candidate-1")
        order_id = record.robot_state["execution"]["limit_order_id"]
        self.executor.cancel_limit(PaperLimitCancelRequest(
            ClientActionId("external-cancel-simulation"),
            SYMBOL,
            order_id,
        ))

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        invalidated = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(invalidated.status, "INVALIDATED")
        self.assertEqual(
            invalidated.robot_state["execution"]["stopped_without_entry_reason"],
            "ENTRY_LIMIT_INACTIVE_BEFORE_FILL",
        )
        self.assertIsNone(
            self.store.get_robot_trade("robot-trade-candidate-1")
        )

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
        # Ground truth for the D2.3 ownership attestation: whatever the
        # authoritative position projection actually is right after the
        # fill, before _finalize_trade() reads it again for entry_quantity/
        # entry_position_version.
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        entry_projection = self.store.get_position_projection(position_key)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_path, "LIMIT")
        self.assertEqual(trade.actual_wv, Decimal("1"))
        self.assertEqual(trade.average_entry, Decimal("81"))
        # D2.3 ownership attestation (owner-frozen convention): must be
        # exactly the authoritative projection's own quantity/version, not
        # any derived or re-guessed value.
        self.assertEqual(trade.entry_quantity, entry_projection.quantity.value)
        self.assertEqual(trade.entry_position_version, entry_projection.version)
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

    def test_existing_open_owner_blocks_first_limit_without_invalidating_candidate(self):
        self._create_candidate(candidate_id="owner")
        self._drive_to_retest_detected("owner")
        self.monitor.tick()
        owner_order_id = self.store.get_robot_candidate("owner").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            owner_order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"),
        )
        self.monitor.tick()
        self.assertEqual(self.store.get_robot_candidate("owner").status, "OPEN")

        self._create_candidate(candidate_id="candidate-2", reference_price=101.0)
        self._drive_to_retest_detected("candidate-2")
        prior_limit_count = len(self.executor.limit_calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())
        self.assertEqual(len(self.executor.limit_calls), prior_limit_count)
        blocked = self.store.get_robot_candidate("candidate-2")
        self.assertEqual(blocked.status, "APPROVED")
        self.assertNotIn("limit_order_id", blocked.robot_state.get("execution") or {})


    def test_second_same_symbol_candidate_never_gets_a_competing_working_entry(self):
        self._create_candidate(candidate_id="candidate-a")
        self._drive_to_retest_detected("candidate-a")
        self.monitor.tick()
        first = self.store.get_robot_candidate("candidate-a")
        self.assertEqual(first.robot_state["execution"]["limit_order_id"], "test-limit-1")

        candidate_b = self._create_candidate(
            candidate_id="candidate-b", reference_price=101.0,
        )
        # Seed candidate-b at the same already-proven RETEST_DETECTED point
        # without replaying the shared-symbol candle feed: candidate-a now
        # legitimately consumes that same latest candle too while maintaining
        # its working LIMIT, whereas production's provider is non-consuming.
        state_b = dict(first.robot_state)
        state_b.pop("execution", None)
        self.store.save_robot_candidate_state(
            candidate_b.candidate_id,
            status="APPROVED",
            robot_state=state_b,
            expected_revision=candidate_b.state_revision,
            updated_at_ms=self.clock(),
        )
        # Both same-symbol candidates observe the same latest closed candle in
        # production; the FIFO test feed needs one identical copy per reader.
        followup = _candle_at(105, high=99, low=97, close=98)
        self.feed.push(SYMBOL, followup)
        self.feed.push(SYMBOL, dict(followup))
        prior_limit_count = len(self.executor.limit_calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-b",))
        self.assertEqual(len(self.executor.limit_calls), prior_limit_count)
        blocked = self.store.get_robot_candidate("candidate-b")
        self.assertEqual(blocked.status, "INVALIDATED")
        self.assertIn(
            "FOREIGN_WORKING_ORDER_PRESENT_BEFORE_ROBOT_ENTRY",
            blocked.robot_state["execution"]["stopped_without_entry_reason"],
        )
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(
            (runtime.mode, runtime.recovery_status),
            ("ROBOT_RUNNING", "READY"),
        )

    def test_foreign_fill_race_is_never_adopted_or_blind_closed(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate(
            "candidate-1"
        ).robot_state["execution"]["limit_order_id"]

        # Simulate a manual fill landing after Robot submitted its LIMIT but
        # before Robot's own LIMIT fill is finalized. No monitor tick occurs
        # between the two fills: this is the narrow race the pre-entry gate
        # alone cannot prevent.
        self.executor._apply_fill(
            SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("80"),
            order_id=OrderId("manual-race-order"),
        )
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"),
        )

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual(self.executor.protection_calls, [])
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(
            (runtime.mode, runtime.recovery_status),
            ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        )
        self.assertIn("ROBOT_ENTRY_OWNERSHIP_MISMATCH", runtime.reason)
        projection = self.store.get_position_projection(
            PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        )
        self.assertEqual(projection.quantity.value, Decimal("2"))
    def test_duplicate_owner_race_during_protection_failure_never_blind_closes(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        self.executor.fail_create_stop = True

        with patch.object(
            RobotBreakoutMonitor,
            "_active_other_owner_candidate_ids",
            side_effect=[(), ("candidate-owner",)],
        ):
            advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.store.get_robot_candidate("candidate-1").status, "APPROVED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertNotIn("full_close", [name for name, _ in self.executor.protection_calls])
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(
            (runtime.mode, runtime.recovery_status),
            ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        )
        self.assertIn("candidate-owner", runtime.reason)

    def test_batusdt_like_wrong_side_structural_extreme_falls_back_and_protects(self):
        """Regression for the real BATUSDT PAPER acceptance defect: the frozen
        structural extreme (lower_touch_points) can end up on the wrong side
        of -- or equal to -- the actual fill's average_entry by the time the
        LIMIT fills (retest slippage, later touches). structural_stop() must
        fall back to the 2% distance rather than raise, so the filled
        position still gets a valid STOP/TAKE and a robot_trade, instead of
        being left open and unprotected."""
        # lower_touch_points min = 85.0 -- above the 81 fill price used below,
        # exactly the "structural candidate on the wrong side of entry" shape.
        self._create_candidate(lower_touch_prices=(85.0, 86.0))
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
        # Fallback: entry * (1 - 2%) = 81 * 0.98 = 79.38, not the (invalid,
        # above-entry) structural candidate 85.0 - 0.1 = 84.9.
        self.assertEqual(trade.stop_price, Decimal("79.38"))
        self.assertLess(trade.stop_price, trade.average_entry)
        self.assertEqual(trade.take_price, Decimal("118"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.LONG)

    def test_pre_plan_exception_after_fill_triggers_emergency_close(self):
        """Any ordinary exception in the post-fill region BEFORE
        build_protection_plan() is even reached (here: _frozen_prices()) must
        fail closed exactly like a plan-validation error does -- the whole
        derive-build-submit region is one fail-closed unit."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))

        with patch.object(
            RobotBreakoutMonitor, "_frozen_prices",
            side_effect=RuntimeError("boom: pre-plan derivation failure"),
        ):
            advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)

    def test_submit_initial_protection_raises_triggers_emergency_close(self):
        """A raised exception during submission (not just a non-COMPLETED
        result) must also fail closed, never leave the fill open."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))

        self.executor.fail_create_stop = True
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)

    def test_protection_plan_failure_after_fill_closes_flat_without_robot_trade(self):
        """A filled Robot position whose initial protection plan cannot be
        built at all (here: frozen_take_90() rejects a degenerate zero-width
        signal, independent of the structural_stop fallback) must never sit
        open and unprotected waiting for a retry. Once the emergency close
        actually completes and the account authoritatively reads back FLAT,
        RobotBreakoutMonitor must create no robot_trade and invalidate the
        candidate so it can never re-enter the same setup."""
        self._create_candidate(start_width=0.0)  # target == reference -> frozen_take_90() rejects
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]

        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        advanced = self.monitor.tick()

        # The tick did act on this candidate (fail-closed emergency close +
        # invalidation is itself a durable state change), just not into OPEN.
        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["full_close"],
        )
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)
        self.assertIn("protection_failure", record.robot_state["execution"])
        self.assertEqual(
            record.robot_state["execution"]["emergency_close_outcome"],
            robot_protection.RECOVERY_CLOSED,
        )

        # INVALIDATED is terminal: the outer tick() loop must never revisit
        # this candidate, so it can never attempt to re-enter the same setup.
        self.feed.push(SYMBOL, _candle_at(105, high=99, low=97, close=98))
        second_advance = self.monitor.tick()
        self.assertEqual(second_advance, ())
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["full_close"],
        )

    def test_full_close_non_completed_leaves_candidate_recoverable(self):
        """An incomplete/rejected/unavailable close must never terminalize
        the candidate prematurely -- the position may still be open."""
        self._create_candidate(start_width=0.0)  # forces the same plan failure as above
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))

        self.executor.full_close_status = CommandResultStatus.REJECTED
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertTrue(record.robot_state["execution"]["emergency_close_pending"])
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.LONG)

    def test_full_close_completed_but_still_non_flat_leaves_candidate_recoverable(self):
        """A close that reports COMPLETED but the authoritative position
        somehow still reads back non-flat must also not terminalize --
        only a proven FLAT may invalidate the candidate."""
        self._create_candidate(start_width=0.0)
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))

        self.executor.full_close_flattens = False  # status stays COMPLETED
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertTrue(record.robot_state["execution"]["emergency_close_pending"])
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.LONG)

    def test_repeated_tick_during_pending_emergency_close_is_idempotent_and_no_new_entry(self):
        """While an emergency close is pending (ambiguous outcome), repeated
        ticks must keep reconciling the same close -- never open a new entry
        -- and once the close genuinely completes and reads back FLAT, the
        candidate becomes terminal exactly once."""
        self._create_candidate(start_width=0.0)
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        limit_calls_before = list(self.executor.limit_calls)
        market_calls_before = list(self.executor.market_calls)

        self.executor.full_close_status = CommandResultStatus.REJECTED
        first_advance = self.monitor.tick()
        self.assertEqual(first_advance, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertEqual(self.executor.limit_calls, limit_calls_before)  # no duplicate LIMIT
        self.assertEqual(self.executor.market_calls, market_calls_before)  # no duplicate Market entry

        # Recovery: the exchange/runtime now genuinely accepts the close.
        self.executor.full_close_status = CommandResultStatus.COMPLETED
        second_advance = self.monitor.tick()

        self.assertEqual(second_advance, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["full_close", "full_close"],
        )
        # Both attempts used the exact same deterministic action id.
        first_request, second_request = (
            call[1] for call in self.executor.protection_calls
        )
        self.assertEqual(first_request.client_action_id, second_request.client_action_id)
        self.assertEqual(self.executor.limit_calls, limit_calls_before)
        self.assertEqual(self.executor.market_calls, market_calls_before)

        # Terminal: a further tick must not attempt yet another close.
        third_advance = self.monitor.tick()
        self.assertEqual(third_advance, ())
        self.assertEqual(len(self.executor.protection_calls), 2)


    def test_finalize_trade_fences_without_protection_when_entry_projection_is_missing(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate(
            "candidate-1"
        ).robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"),
        )

        store = self.monitor._store()
        with patch.object(store, "get_position_projection", return_value=None):
            advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual(self.executor.protection_calls, [])
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(runtime.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertIn("ROBOT_ENTRY_OWNERSHIP_MISMATCH", runtime.reason)

    def test_finalize_trade_fences_without_protection_when_position_was_flattened(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate(
            "candidate-1"
        ).robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"),
        )

        # A foreign/manual close lands before Robot can adopt the fill.
        # Entry ownership is now ambiguous and must fence, not place
        # protection or issue another aggregate close.
        self.executor._flatten(SYMBOL)
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(
            self.store.get_robot_candidate("candidate-1").status,
            "APPROVED",
        )
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual(self.executor.protection_calls, [])
        runtime = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(runtime.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertIn("ROBOT_ENTRY_OWNERSHIP_MISMATCH", runtime.reason)
    def test_restart_after_partial_fill_finalizes_once_without_market_top_up(self):
        """A restart after authoritative partial fill but before ownership
        commit must recover through the same P0.3 subtractive path: cancel
        remainder, protect the proven fill, and create exactly one owner.
        No fresh candle or Market completion is required."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )

        # Simulate process restart after the fill is durable but before the
        # old monitor has observed/finalized it. The restarted coordinator
        # gets a fresh SQLite connection and no closed candle is queued.
        self.monitor.close()
        self.monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            action_executor=self.executor,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
        )
        feed_calls_before = len(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.feed.calls), feed_calls_before)
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_path, "LIMIT")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(trade.entry_quantity, Decimal("0.6"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )

        # Once the candidate is OPEN, a further tick cannot create a second
        # trade, protection set, cancel, or entry mutation.
        self.assertEqual(self.monitor.tick(), ())
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.market_calls, [])
        self.assertEqual(len(self.executor.protection_calls), 2)
        same_trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertEqual(same_trade, trade)

    def test_event_driven_authoritative_fill_finalizes_without_periodic_tick_or_candle(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        feed_calls_before = len(self.feed.calls)

        advanced = self.monitor.process_authoritative_fill(SYMBOL)

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.feed.calls), feed_calls_before)
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_path, "LIMIT")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(trade.entry_quantity, Decimal("0.6"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )

    def test_first_partial_fill_is_final_limit_trade_without_market_top_up(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]

        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        feed_calls_before = len(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.feed.calls), feed_calls_before)
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.cancel_calls[0].order_id, order_id)
        order = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.filled_quantity, Decimal("0.6"))
        self.assertEqual(self.executor.market_calls, [])

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertIsNotNone(trade)
        self.assertEqual(trade.entry_path, "LIMIT")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(trade.average_entry, Decimal("81"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        projection = self.store.get_position_projection(position_key)
        self.assertEqual(projection.quantity.value, Decimal("0.6"))
        self.assertEqual(trade.entry_quantity, Decimal("0.6"))

    def test_first_partial_fill_protection_failure_fails_closed_without_market_top_up(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]

        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self.executor.fail_create_stop = True
        feed_calls_before = len(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.feed.calls), feed_calls_before)
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.market_calls, [])
        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)

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

    # -- PAUSE / STOP / RECONCILIATION_REQUIRED admission gate --
    #
    # RobotBreakoutMonitor is the sole owner of already-admitted APPROVED
    # candidates (module docstring), but until this gate it never consulted
    # robot_runtime_state at all: a PAUSED or even a fully ROBOT_STOPPED
    # robot could still submit new entry LIMIT/Market orders for candidates
    # approved before the pause/stop -- a real gap surfaced during live
    # PAPER acceptance (NEOUSDT/HAJIMIUSDT LIMIT orders appearing after
    # Robot was PAUSED). These tests cover the authoritative PAUSE=variant-B
    # contract: PAUSE/RECONCILIATION_REQUIRED block and cancel but stay
    # recoverable; ROBOT_STOPPED additionally gives terminal disposition to
    # pending pre-entry intent, per
    # AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md. Protection for
    # an already-filled/open position is never gated by any of this.

    def _set_admission_state(self, mode, recovery_status):
        current = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.store.update_robot_runtime_state(
            ACCOUNT_ID, mode=mode, recovery_status=recovery_status,
            reason=None, expected_version=current.version, updated_at_ms=self.clock(),
        )

    def test_paused_with_no_working_order_never_submits_entry(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self._set_admission_state("ROBOT_RUNNING", "PAUSED")

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertNotIn("limit_order_id", record.robot_state.get("execution") or {})

    def test_pause_cancels_working_entry_limit_and_creates_no_position(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT while still READY
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.assertEqual(len(self.executor.limit_calls), 1)

        self._set_admission_state("ROBOT_RUNNING", "PAUSED")
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.cancel_calls[0].order_id, order_id)
        order = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.executor.market_calls, [])
        self.assertEqual(self.executor.protection_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")  # recoverable, never invalidated by PAUSE
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertIsNone(self.store.get_position_projection(position_key))

        # A later tick while still PAUSED does not resubmit.
        self.monitor.tick()
        self.assertEqual(len(self.executor.limit_calls), 1)

    def test_paused_does_not_disturb_an_already_open_robot_position(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))
        self.monitor.tick()  # finalizes -> OPEN, STOP/TAKE submitted
        before = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(before.status, "OPEN")
        protection_before = list(self.executor.protection_calls)

        self._set_admission_state("ROBOT_RUNNING", "PAUSED")
        advanced = self.monitor.tick()

        # tick()'s own status=="APPROVED" filter skips this OPEN candidate
        # entirely -- PAUSE introduces no new suppression of it, and no new
        # one is needed: existing STOP/TAKE/protection/recovery ownership
        # for an OPEN position lives outside this monitor.
        self.assertEqual(advanced, ())
        after = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(after.status, "OPEN")
        self.assertEqual(after.state_revision, before.state_revision)
        self.assertEqual(after.robot_state, before.robot_state)
        self.assertEqual(self.executor.protection_calls, protection_before)

    def test_robot_stopped_before_any_entry_order_invalidates_the_candidate(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertIn("stopped_without_entry_reason", record.robot_state["execution"])

    def test_robot_stopped_cancels_and_invalidates_a_still_unfilled_working_entry_limit(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT while still READY
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]

        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(len(self.executor.cancel_calls), 1)
        self.assertEqual(self.executor.cancel_calls[0].order_id, order_id)
        order = self.store.get_paper_limit(order_id, ACCOUNT_ID)
        self.assertEqual(order.status, "cancelled")
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")

    def test_restart_after_stop_never_revives_an_invalidated_candidate(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")
        self.monitor.tick()  # invalidates candidate-1
        self.assertEqual(self.store.get_robot_candidate("candidate-1").status, "INVALIDATED")

        # Restart: durable admission returns to (ROBOT_RUNNING, READY),
        # exactly what start_robot()/RobotRecoveryCoordinator.start() would
        # durably establish. This monitor never decides restart itself; it
        # only reacts to the same authoritative robot_runtime_state.
        self._set_admission_state("ROBOT_RUNNING", "READY")
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())  # tick()'s APPROVED-only filter permanently skips it
        self.assertEqual(self.executor.limit_calls, [])
        self.assertEqual(self.store.get_robot_candidate("candidate-1").status, "INVALIDATED")

        # Only a genuinely new candidate (a new explicit approval) creates
        # new work after restart. A different symbol keeps its signal
        # snapshot distinct from candidate-1's (durable admission dedupes
        # identical snapshots by content hash).
        self._create_candidate("candidate-2", symbol="OTHERUSDT")
        self.monitor.tick()
        record2 = self.store.get_robot_candidate("candidate-2")
        self.assertEqual(record2.status, "APPROVED")
        self.assertEqual(record2.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)

    def test_reconciliation_required_blocks_new_entry_submission(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self._set_admission_state("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ())
        self.assertEqual(self.executor.limit_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        # Never invalidated by RECONCILIATION_REQUIRED -- only ROBOT_STOPPED
        # gives terminal disposition; this candidate stays recoverable.
        self.assertEqual(record.status, "APPROVED")

    def test_reconciliation_required_does_not_block_protection_of_an_already_filled_entry(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT while still READY
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))

        # The fill already exists before reconciliation is required (e.g. it
        # filled, then something elsewhere triggered RECONCILIATION_REQUIRED
        # before this monitor's next tick) -- finalize/protection must still
        # run: RECONCILIATION_REQUIRED blocks only NEW entry risk.
        self._set_admission_state("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        self.assertIsNotNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )

    def test_paused_partial_fill_finalizes_actual_quantity_instead_of_waiting_for_market_top_up(self):
        """A fill that exists before PAUSE is observed still finalizes the
        actual LIMIT-filled quantity immediately; PAUSE blocks only new risk.
        P0.3 removes the old wait/top-up phase entirely."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self._set_admission_state("ROBOT_RUNNING", "PAUSED")
        calls_before = list(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.feed.calls, calls_before)
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertEqual(trade.entry_path, "LIMIT")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )
        self.assertEqual(self.store.get_robot_runtime_state(ACCOUNT_ID).recovery_status, "PAUSED")

    def test_robot_stopped_partial_fill_finalizes_actual_quantity_never_orphaning_exposure(self):
        """ROBOT_STOPPED cannot invalidate a candidate that already has real
        exposure; P0.3 finalizes and protects that actual LIMIT fill instead."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")
        calls_before = list(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.feed.calls, calls_before)
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )

    def test_paused_partial_fill_protection_failure_uses_fail_closed_emergency_close(self):
        """Protection failure after a partial fill still uses the existing
        fail-closed emergency close while PAUSED, with no Market top-up."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self._set_admission_state("ROBOT_RUNNING", "PAUSED")
        self.executor.fail_create_stop = True

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.market_calls, [])
        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(
            record.robot_state["execution"]["emergency_close_outcome"],
            robot_protection.RECOVERY_CLOSED,
        )
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)

    # -- Partial-fill protection must never depend on a new closed candle --
    #
    # AUTOPILOT_ROBOT_V0_1_RECOVERY_STATE_BATCH_DECISION.md Section 6's
    # 5-second STOP-not-proven window is a maximum recovery deadline, not a
    # retry interval -- it must never collapse into "wait for
    # RobotBreakoutMonitor's next tick_interval_s (60s in production)
    # opportunity, which itself may further depend on a new 1m candle
    # closing." structural_extreme/frozen_prices/structural_stop and
    # average_entry (the authoritative position projection) are all already
    # frozen/durable and need no live market data at all -- these tests
    # drive the finalize tick with NO candle queued (get_closed_candle()
    # returns None) to prove the immediate-protect path never reaches that
    # call at all.

    def test_paused_partial_fill_protects_immediately_with_no_closed_candle_available(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self._set_admission_state("ROBOT_RUNNING", "PAUSED")
        calls_before = list(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls],
            ["create_stop", "create_take"],
        )
        self.assertEqual(self.feed.calls, calls_before)

    def test_robot_stopped_partial_fill_protects_immediately_with_no_closed_candle_available(self):
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")
        calls_before = list(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.executor.market_calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "OPEN")
        trade = self.store.get_robot_trade("robot-trade-candidate-1")
        self.assertEqual(trade.actual_wv, Decimal("0.6"))
        self.assertEqual(self.feed.calls, calls_before)

    def test_paused_partial_fill_no_candle_and_protection_failure_emergency_closes_immediately(self):
        """No candle plus protection failure must emergency-close in the same
        observation pass after first fill; no wait and no Market completion."""
        self._create_candidate()
        self._drive_to_retest_detected()
        self.monitor.tick()
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(
            order_id, SYMBOL, OrderSide.BUY, Decimal("0.6"), Decimal("81"),
        )
        self._set_admission_state("ROBOT_RUNNING", "PAUSED")
        self.executor.fail_create_stop = True
        calls_before = list(self.feed.calls)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.feed.calls, calls_before)
        self.assertEqual(self.executor.market_calls, [])
        self.assertEqual([name for name, _ in self.executor.protection_calls], ["full_close"])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(
            record.robot_state["execution"]["emergency_close_outcome"],
            robot_protection.RECOVERY_CLOSED,
        )
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))
        position_key = PositionKey(ACCOUNT_ID, Category.LINEAR, Symbol(SYMBOL), 0)
        self.assertEqual(self.store.get_position_projection(position_key).side, PositionSide.FLAT)

    def test_fail_closed_emergency_close_still_operates_when_robot_stopped(self):
        """CR-PAPER-PROTECTION-LIFECYCLE-001 (PR #89) fail-closed behavior
        must survive this gate unchanged: a fill whose protection plan
        raises still triggers submit_emergency_close()'s sanctioned full
        close, exactly as before, regardless of durable admission state."""
        self._create_candidate(lower_touch_prices=())  # no counted touches -> _structural_extreme raises
        self._drive_to_retest_detected()
        self.monitor.tick()  # submits the initial LIMIT while still READY
        order_id = self.store.get_robot_candidate("candidate-1").robot_state["execution"]["limit_order_id"]
        self.executor.fill_resting_limit(order_id, SYMBOL, OrderSide.BUY, Decimal("1"), Decimal("81"))

        self._set_admission_state("ROBOT_STOPPED", "ROBOT_STOPPED")
        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(
            [name for name, _ in self.executor.protection_calls], ["full_close"],
        )
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(
            record.robot_state["execution"]["emergency_close_outcome"],
            robot_protection.RECOVERY_CLOSED,
        )
        self.assertIsNone(self.store.get_robot_trade("robot-trade-candidate-1"))

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
