from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import robot_state_machine
from scanner_geometry_cursor import (
    build_scanner_geometry_cursor_anchor,
    latest_scanner_closed_candle,
)
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT_ID = TradingAccountId("paper")
SYMBOL = "TESTUSDT"
T0_MS = 1_800_000


def _snapshot(*, apex_index=130):
    return {
        "symbol": SYMBOL,
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
        "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
            geometry_index=100,
            source_candle_time_ms=T0_MS,
            timeframe="1",
        ),
    }


def _candle(index, *, high, low, close):
    return {
        "closed": True,
        "timeframe": "1",
        "geometry_index": index,
        "time_ms": T0_MS + (index - 100) * 60_000,
        "high": high,
        "low": low,
        "close": close,
    }


class _Clock:
    def __init__(self):
        self.value = 1000

    def __call__(self):
        self.value += 1
        return self.value


class _NoEntryExecutor:
    def __init__(self):
        self.calls = []

    def _unexpected(self, name):
        self.calls.append(name)
        raise AssertionError(f"unexpected execution side effect: {name}")

    def create_limit(self, request):
        return self._unexpected("create_limit")

    def cancel_limit(self, request):
        return self._unexpected("cancel_limit")

    def market(self, request):
        return self._unexpected("market")

    def create_stop(self, request):
        return self._unexpected("create_stop")

    def amend_stop(self, request):
        return self._unexpected("amend_stop")

    def create_take(self, request):
        return self._unexpected("create_take")

    def amend_take(self, request):
        return self._unexpected("amend_take")

    def full_close(self, request):
        return self._unexpected("full_close")


class RobotBreakoutMonitorAdmissionCatchupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "terminal.db"
        self.store = SQLiteStore.open(self.db_path)
        self.clock = _Clock()
        self.executor = _NoEntryExecutor()
        self.monitor = None

    def tearDown(self):
        if self.monitor is not None:
            self.monitor.close()
        self.store.close()
        self.temp_dir.cleanup()

    def _create_candidate(self, *, apex_index=130):
        snapshot = _snapshot(apex_index=apex_index)
        candidate, created = self.store.create_robot_candidate(
            candidate_id="candidate-1",
            trading_account_id=ACCOUNT_ID,
            symbol=Symbol(SYMBOL),
            status="APPROVED",
            signal_snapshot=snapshot,
            approved_at_ms=1,
            updated_at_ms=1,
        )
        self.assertTrue(created)
        self.assertIsNone(candidate.robot_state)
        return snapshot

    def _monitor(self, catchup_provider, *, get_closed_candle=None):
        monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT_ID,
            get_closed_candle=get_closed_candle or (lambda _symbol: None),
            action_executor=self.executor,
            tick_size_provider=lambda _symbol: self.fail("tick size must not be read"),
            clock_ms=self.clock,
            get_admission_catchup_candles=catchup_provider,
        )
        self.monitor = monitor
        return monitor

    def test_no_breakout_persists_waiting_breakout_once(self):
        self._create_candidate()
        calls = []

        def provider(symbol, signal_snapshot):
            calls.append((symbol, signal_snapshot["geometry"]["current_index"]))
            return (
                _candle(101, high=96, low=94, close=95),
                _candle(102, high=97, low=95, close=96),
            )

        monitor = self._monitor(provider)
        self.assertEqual(monitor.tick(), ("candidate-1",))

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
        self.assertEqual(record.robot_state["geometry_cursor"], 102)
        self.assertEqual(calls, [(SYMBOL, 100)])
        self.assertEqual(self.executor.calls, [])

        # Catch-up is admission-only: once durable state exists, ordinary
        # runtime monitoring owns later candles and no historical replay runs.
        self.assertEqual(monitor.tick(), ())
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.get_robot_candidate("candidate-1").state_revision, 1)

    def test_breakout_only_persists_waiting_retest(self):
        self._create_candidate()
        monitor = self._monitor(lambda _symbol, _snapshot: (
            _candle(101, high=96, low=94, close=95),
            _candle(102, high=106, low=97, close=105),
            _candle(103, high=108, low=100, close=104),
        ))

        self.assertEqual(monitor.tick(), ("candidate-1",))

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertEqual(record.robot_state["breakout_index"], 102)
        self.assertNotIn("execution", record.robot_state)
        self.assertEqual(self.executor.calls, [])

    def test_breakout_and_retest_persist_late_marker_without_any_entry_order(self):
        snapshot = self._create_candidate()
        monitor = self._monitor(lambda _symbol, _snapshot: (
            _candle(101, high=96, low=94, close=95),
            _candle(102, high=106, low=97, close=105),
            _candle(103, high=101, low=95, close=98),
        ))

        self.assertEqual(monitor.tick(), ("candidate-1",))

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)
        self.assertEqual(record.robot_state["breakout_index"], 102)
        self.assertEqual(record.robot_state["retest_index"], 103)
        self.assertEqual(
            record.robot_state["execution"]["entry_mode"],
            LATE_ADMISSION_MARKET,
        )
        self.assertEqual(record.signal_snapshot["geometry"], snapshot["geometry"])
        self.assertEqual(self.executor.calls, [])

        # This microslice intentionally does not execute the late entry on a
        # later tick either. The durable marker waits for the next slice.
        self.assertEqual(monitor.tick(), ())
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.state_revision, 1)
        self.assertNotIn("limit_order_id", record.robot_state["execution"])
        self.assertEqual(self.executor.calls, [])

    def test_apex_reached_persists_expired_once(self):
        self._create_candidate(apex_index=104)
        monitor = self._monitor(lambda _symbol, _snapshot: (
            _candle(104, high=99, low=97, close=98),
        ))

        self.assertEqual(monitor.tick(), ("candidate-1",))

        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.status, "EXPIRED")
        self.assertEqual(record.state_revision, 1)
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_EXPIRED_AT_APEX)
        self.assertEqual(record.robot_state["geometry_cursor"], 104)
        self.assertEqual(self.executor.calls, [])

    def test_provider_failure_persists_nothing_and_retries_later(self):
        self._create_candidate()
        attempts = []

        def provider(_symbol, _snapshot):
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise RuntimeError("catch-up unavailable")
            return ()

        monitor = self._monitor(provider)

        self.assertEqual(monitor.tick(), ())
        failed = self.store.get_robot_candidate("candidate-1")
        self.assertIsNone(failed.robot_state)
        self.assertEqual(failed.state_revision, 0)
        self.assertEqual(self.executor.calls, [])

        self.assertEqual(monitor.tick(), ("candidate-1",))
        recovered = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(recovered.state_revision, 1)
        self.assertEqual(recovered.robot_state["phase"], robot_state_machine.PHASE_WAITING_BREAKOUT)
        self.assertEqual(attempts, [1, 2])

    def test_replay_failure_persists_nothing(self):
        self._create_candidate()
        monitor = self._monitor(lambda _symbol, _snapshot: (
            _candle(101, high=96, low=94, close=95),
        ))

        with patch(
            "terminal.application.robot_breakout_monitor.replay_admission_catchup",
            side_effect=RuntimeError("replay failed"),
        ):
            self.assertEqual(monitor.tick(), ())

        record = self.store.get_robot_candidate("candidate-1")
        self.assertIsNone(record.robot_state)
        self.assertEqual(record.state_revision, 0)
        self.assertEqual(self.executor.calls, [])

    def test_restart_with_durable_state_does_not_run_admission_catchup_again(self):
        self._create_candidate()
        first = self._monitor(lambda _symbol, _snapshot: ())
        self.assertEqual(first.tick(), ("candidate-1",))
        first.close()
        self.monitor = None

        restart_calls = []

        def must_not_run(_symbol, _snapshot):
            restart_calls.append(True)
            raise AssertionError("restart must not replay admission history")

        restarted = self._monitor(must_not_run)
        self.assertEqual(restarted.tick(), ())
        self.assertEqual(restart_calls, [])
        self.assertEqual(self.store.get_robot_candidate("candidate-1").state_revision, 1)

    def test_canonical_scanner_provider_auto_wires_historical_catchup(self):
        self._create_candidate()
        with patch(
            "terminal.application.robot_breakout_monitor.load_scanner_catchup_closed_candles",
            return_value=(
                _candle(101, high=96, low=94, close=95),
                _candle(102, high=106, low=97, close=105),
            ),
        ) as history:
            monitor = RobotBreakoutMonitor(
                lambda: SQLiteStore.open(self.db_path),
                ACCOUNT_ID,
                get_closed_candle=latest_scanner_closed_candle,
                action_executor=self.executor,
                tick_size_provider=lambda _symbol: self.fail("tick size must not be read"),
                clock_ms=self.clock,
            )
            self.monitor = monitor
            self.assertEqual(monitor.tick(), ("candidate-1",))

        history.assert_called_once()
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.robot_state["phase"], robot_state_machine.PHASE_WAITING_RETEST)
        self.assertEqual(self.executor.calls, [])


if __name__ == "__main__":
    unittest.main()
