from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import robot_state_machine
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.api.models import CommandResultStatus
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.domain.models import Price, Quantity, Symbol, TradingAccountId
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("paper")
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
            "touches": {
                "lower_touch_points": [
                    {"index": 99, "price": 90.0, "counted": True},
                ],
                "upper_touch_points": [
                    {"index": 99, "price": 110.0, "counted": True},
                ],
            },
            "pair_metrics": {
                "reference_price": 94.0,
                "start_width": 10.0,
            },
        },
        "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
            geometry_index=100,
            source_candle_time_ms=T0_MS,
            timeframe="1",
        ),
    }


def _late_state():
    return {
        "state_version": robot_state_machine.STATE_VERSION,
        "phase": robot_state_machine.PHASE_RETEST_DETECTED,
        "pattern": "Falling Wedge",
        "direction": robot_state_machine.DIRECTION_LONG,
        "apex_index": 130,
        "geometry_cursor": 103,
        "breakout_index": 102,
        "retest_index": 103,
        "last_event": robot_state_machine.EVENT_RETEST,
        "execution": {"entry_mode": LATE_ADMISSION_MARKET},
    }


def _book():
    return NormalizedOrderBook(
        symbol=Symbol(SYMBOL),
        bids=(PriceLevel(Price(Decimal("99")), Quantity(Decimal("10"))),),
        asks=(PriceLevel(Price(Decimal("100")), Quantity(Decimal("10"))),),
        health=BookHealth.READY,
        received_at_ms=1_500,
        available_depth=1,
    )


class _Clock:
    def __init__(self):
        self.value = 1_600

    def __call__(self):
        self.value += 1
        return self.value


class _NoopExecutor:
    def create_limit(self, request):
        raise AssertionError("ordinary LIMIT path must not run")

    def cancel_limit(self, request):
        raise AssertionError("cancel path must not run")

    def create_stop(self, request):
        raise AssertionError("protection must not run without authoritative fill")

    def amend_stop(self, request):
        raise AssertionError("protection must not run")

    def create_take(self, request):
        raise AssertionError("protection must not run without authoritative fill")

    def amend_take(self, request):
        raise AssertionError("protection must not run")

    def full_close(self, request):
        raise AssertionError("close must not run")


class RobotBreakoutMonitorLateAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "terminal.db"
        self.store = SQLiteStore.open(self.db_path)
        runtime = self.store.initialize_robot_runtime_state(ACCOUNT, updated_at_ms=1)
        self.store.update_robot_runtime_state(
            ACCOUNT,
            mode="ROBOT_RUNNING",
            recovery_status="READY",
            reason=None,
            expected_version=runtime.version,
            updated_at_ms=2,
        )
        candidate, created = self.store.create_robot_candidate(
            candidate_id="candidate-1",
            trading_account_id=ACCOUNT,
            symbol=Symbol(SYMBOL),
            status="APPROVED",
            signal_snapshot=_snapshot(),
            approved_at_ms=3,
            updated_at_ms=3,
        )
        self.assertTrue(created)
        self.store.save_robot_candidate_state(
            candidate.candidate_id,
            status="APPROVED",
            robot_state=_late_state(),
            expected_revision=candidate.state_revision,
            updated_at_ms=4,
        )
        self.clock = _Clock()
        self.submissions = []
        self.monitor = None

    def tearDown(self):
        if self.monitor is not None:
            self.monitor.close()
        self.store.close()
        self.temp.cleanup()

    def _closed_candle(self, _symbol):
        return {"time_ms": T0_MS + 4 * 60_000}

    def _monitor(self, *, normalized_quantity=Decimal("1")):
        def preflight(request, identity):
            return SimpleNamespace(
                admitted=True,
                normalized_quantity=normalized_quantity,
                identity=identity,
            )

        def submit(request, identity):
            # Strict ordering proof: candidate intent must already be committed
            # and visible through another store connection before side effect.
            durable = self.store.get_robot_candidate("candidate-1")
            intent = durable.robot_state["execution"].get("late_market_intent")
            self.assertIsNotNone(intent)
            self.assertEqual(intent["client_action_id"], request.client_action_id.value)
            self.assertEqual(intent["command_id"], identity.command_id.value)
            self.assertEqual(intent["order_link_id"], identity.order_link_id)
            self.submissions.append((request, identity))
            return SimpleNamespace(status=CommandResultStatus.COMPLETED)

        self.monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.db_path),
            ACCOUNT,
            get_closed_candle=self._closed_candle,
            action_executor=_NoopExecutor(),
            tick_size_provider=lambda _symbol: Decimal("0.1"),
            clock_ms=self.clock,
            get_market_book=lambda _symbol: _book(),
            market_preflight=preflight,
            submit_market=submit,
        )
        return self.monitor

    def test_viable_late_admission_persists_intent_before_submit_and_reuses_identity(self):
        monitor = self._monitor()

        self.assertEqual(monitor.tick(), ("candidate-1",))
        first = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(first.state_revision, 2)
        intent = first.robot_state["execution"]["late_market_intent"]
        self.assertEqual(intent["normalized_quantity"], "1")
        self.assertEqual(intent["sizing_reference_price"], "100")
        self.assertEqual(len(self.submissions), 1)

        # No position projection exists in this isolated orchestration test, so
        # the next tick safely replays the SAME durable Market identity.
        self.assertEqual(monitor.tick(), ("candidate-1",))
        second = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(second.state_revision, 2)
        self.assertEqual(len(self.submissions), 2)
        self.assertEqual(
            self.submissions[0][0].client_action_id,
            self.submissions[1][0].client_action_id,
        )
        self.assertEqual(self.submissions[0][1], self.submissions[1][1])

    def test_insufficient_liquidity_from_canonical_preflight_quantity_persists_no_intent(self):
        monitor = self._monitor(normalized_quantity=Decimal("11"))

        self.assertEqual(monitor.tick(), ())
        record = self.store.get_robot_candidate("candidate-1")
        self.assertEqual(record.state_revision, 1)
        self.assertNotIn("late_market_intent", record.robot_state["execution"])
        self.assertEqual(self.submissions, [])


if __name__ == "__main__":
    unittest.main()
