from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import robot_state_machine
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT_ID = TradingAccountId("paper")
SYMBOL = "TESTUSDT"
T0_MS = 1_800_000


def _snapshot(*, symbol=SYMBOL, apex_index=130, current_index=100, anchor_index=None):
    anchor_index = current_index if anchor_index is None else anchor_index
    return {
        "symbol": symbol,
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": current_index,
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


class _RecordingLimitSubmitter:
    def __init__(self):
        self.calls: list = []

    def create_limit(self, request):
        self.calls.append(request)
        return request


class _Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        self.value += 1
        return self.value


class RobotBreakoutMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp_dir.name) / "terminal.db")
        self.feed = _ScriptedCandleFeed()
        self.submitter = _RecordingLimitSubmitter()
        self.clock = _Clock()
        self.monitor = RobotBreakoutMonitor(
            self.store,
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            limit_submitter=self.submitter,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
        )

    def tearDown(self):
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

    def test_lazily_initializes_missing_robot_state_without_reading_a_candle(self):
        self._create_candidate()

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        self.assertEqual(self.feed.calls, [])
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "APPROVED")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)

    def test_breakout_then_retest_submits_exactly_one_initial_limit(self):
        self._create_candidate()
        self.monitor.tick()  # initialize

        self.feed.push(SYMBOL, _candle_at(101, high=96, low=94, close=95))
        advanced = self.monitor.tick()
        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
        self.assertEqual(record.robot_state["last_event"], robot_state_machine.EVENT_NO_TRANSITION)

        self.feed.push(SYMBOL, _candle_at(102, high=106, low=97, close=105))
        self.monitor.tick()
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertEqual(record.robot_state["breakout_index"], 102)
        self.assertEqual(self.submitter.calls, [])

        self.feed.push(SYMBOL, _candle_at(103, high=106, low=99, close=104))
        self.monitor.tick()
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertEqual(self.submitter.calls, [])

        self.feed.push(SYMBOL, _candle_at(104, high=101, low=95, close=98))
        self.monitor.tick()
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)
        self.assertEqual(record.robot_state["retest_index"], 104)
        self.assertEqual(record.status, "APPROVED")
        self.assertEqual(len(self.submitter.calls), 1)
        request = self.submitter.calls[0]
        self.assertEqual(request.symbol, SYMBOL)
        self.assertEqual(request.side.value, "Buy")

        # Terminal phase: no candle is consulted, but the LIMIT is idempotently
        # retried every tick using the same deterministic client_action_id.
        self.monitor.tick()
        self.assertEqual(len(self.feed.calls), 4)
        self.assertEqual(len(self.submitter.calls), 2)
        self.assertEqual(
            self.submitter.calls[0].client_action_id, self.submitter.calls[1].client_action_id,
        )

    def test_candidate_expires_at_apex_without_submitting_a_limit(self):
        self._create_candidate(apex_index=100, current_index=100)

        advanced = self.monitor.tick()

        self.assertEqual(advanced, ("candidate-1",))
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "EXPIRED")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)
        self.assertEqual(self.submitter.calls, [])

        # Further ticks are no-ops and never touch the candle feed.
        self.monitor.tick()
        self.assertEqual(self.feed.calls, [])

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
            self.store,
            ACCOUNT_ID,
            get_closed_candle=self.feed,
            limit_submitter=self.submitter,
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


if __name__ == "__main__":
    unittest.main()
