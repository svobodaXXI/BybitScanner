from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest

import robot_state_machine
from scanner_geometry_cursor import build_scanner_geometry_cursor_anchor
from terminal.api.models import CommandResultStatus
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.application.robot_late_admission_market import build_late_admission_market_plan
from terminal.domain.models import (
    Category, PositionKey, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_http_server import SerializedPaperRuntime
from terminal.runtime.paper_runtime import PaperRuntime


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


class _FreshBookProvider:
    def __init__(self):
        self.thread_ids: list[int] = []

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        self.thread_ids.append(threading.get_ident())
        if symbol != Symbol(SYMBOL):
            return None
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("99")), Quantity(Decimal("1000"))),),
            asks=(PriceLevel(Price(Decimal("100")), Quantity(Decimal("1000"))),),
            health=BookHealth.READY,
            received_at_ms=int(time.time() * 1000),
            available_depth=1,
        )

    def get_current_book_update(self, symbol: Symbol):
        return None


def _runtime_book() -> NormalizedOrderBook:
    return NormalizedOrderBook(
        symbol=Symbol(SYMBOL),
        bids=(PriceLevel(Price(Decimal("99")), Quantity(Decimal("1000"))),),
        asks=(PriceLevel(Price(Decimal("100")), Quantity(Decimal("1000"))),),
        health=BookHealth.READY,
        received_at_ms=int(time.time() * 1000),
        available_depth=1,
    )


def _runtime_instrument(symbol: str = SYMBOL) -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR,
        symbol,
        "LinearPerpetual",
        "Trading",
        "TEST",
        "USDT",
        "USDT",
        Decimal("0.1"),
        Decimal("1000000"),
        Decimal("0.1"),
        Decimal("0.001"),
        Decimal("1000000"),
        Decimal("1000000"),
        Decimal("0.001"),
        Decimal("5"),
    )


def _runtime_closed_candle(_symbol: str):
    return {"time_ms": T0_MS + 4 * 60_000}


def _runtime_geometry_index(_symbol: str, _snapshot: dict[str, object]) -> int:
    return 103


class RobotLateAdmissionSerializedRuntimeAcceptanceTests(unittest.TestCase):
    def test_callbacks_route_to_owner_and_submit_shared_paper_market_with_stable_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "terminal.db"
            instrument = _runtime_instrument()
            book_provider = _FreshBookProvider()
            holder: dict[str, PaperRuntime] = {}

            def factory() -> PaperRuntime:
                owner = PaperRuntime(
                    db_path,
                    book_provider=book_provider,
                    instrument_snapshot=instrument,
                    instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
                    robot_latest_geometry_index_provider=_runtime_geometry_index,
                    robot_closed_candle_provider=_runtime_closed_candle,
                    robot_tick_interval_s=60.0,
                )
                holder["owner"] = owner
                return owner

            runtime = SerializedPaperRuntime(factory)
            try:
                runtime.start_robot_monitor()
                owner_ident = runtime.call(lambda _owner: threading.get_ident())
                owner = holder["owner"]
                plan = build_late_admission_market_plan(
                    {
                        "candidate_id": "candidate-runtime-late-market",
                        "status": "APPROVED",
                        "timeframe": "1",
                        "signal_snapshot": _snapshot(),
                    },
                    _late_state(),
                    _runtime_book(),
                )
                result: dict[str, object] = {}

                def invoke_from_background_thread() -> None:
                    result["worker_ident"] = threading.get_ident()
                    result["book"] = owner._dispatch_robot_market_book(SYMBOL)
                    result["preflight"] = owner._dispatch_robot_market_preflight(
                        plan.request, plan.identity,
                    )
                    result["submit"] = owner._dispatch_robot_market_submit(
                        plan.request, plan.identity,
                    )

                worker = threading.Thread(target=invoke_from_background_thread)
                worker.start()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive(), "late Market wiring deadlocked")
                self.assertNotEqual(result["worker_ident"], owner_ident)
                self.assertEqual(result["book"].symbol, Symbol(SYMBOL))
                self.assertTrue(result["preflight"].admitted)
                self.assertGreater(result["preflight"].normalized_quantity, Decimal("0"))
                self.assertEqual(result["submit"].status, CommandResultStatus.COMPLETED)
                self.assertTrue(book_provider.thread_ids)
                self.assertTrue(
                    all(ident == owner_ident for ident in book_provider.thread_ids),
                    "late Market book/execution escaped the serialized owner thread",
                )

                command = runtime.call(
                    lambda runtime_owner: runtime_owner.store.get_command(
                        plan.identity.command_id
                    )
                )
                self.assertIsNotNone(command)
                self.assertEqual(command.current_state.value, "filled")
                self.assertEqual(command.order_link_id, plan.identity.order_link_id)

                position = runtime.call(
                    lambda runtime_owner: runtime_owner.store.get_position_projection(
                        PositionKey(ACCOUNT, Category.LINEAR, Symbol(SYMBOL), 0)
                    )
                )
                self.assertIsNotNone(position)
                self.assertEqual(position.average_entry.value, Decimal("100"))
                self.assertGreater(position.quantity.value, Decimal("0"))
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
