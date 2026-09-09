from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from robot_state_machine import initialize_state
from terminal.domain.models import Category, Price, Quantity, Symbol, TradingAccountId
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT_ID = TradingAccountId("paper")


class _StaticBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("99")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("101")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=1,
            available_depth=1,
        )


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR,
        "TESTUSDT",
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
        Decimal("1"),
        Decimal("0.001"),
        Decimal("5"),
    )


def _runtime(
    path: Path,
    *,
    latest_geometry_index_provider=None,
) -> PaperRuntime:
    instrument = _instrument()
    return PaperRuntime(
        path,
        book_provider=_StaticBookProvider(),
        instrument_snapshot=instrument,
        instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
        robot_latest_geometry_index_provider=latest_geometry_index_provider,
    )


def _snapshot() -> dict[str, object]:
    return {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 110, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
    }


def _robot_state() -> dict[str, object]:
    state, _ = initialize_state({
        "candidate_id": "candidate-waiting",
        "status": "APPROVED",
        "timeframe": "1",
        "symbol": "TESTUSDT",
        "signal_snapshot": _snapshot(),
    })
    return state


def _set_running(runtime: PaperRuntime) -> None:
    state = runtime.store.get_robot_runtime_state(ACCOUNT_ID)
    if state is None:
        raise AssertionError("PaperRuntime startup must initialize Robot runtime state")
    runtime.store.update_robot_runtime_state(
        ACCOUNT_ID,
        mode="ROBOT_RUNNING",
        recovery_status="READY",
        reason=None,
        expected_version=state.version,
        updated_at_ms=state.updated_at_ms + 1,
    )


class RobotRuntimeWiringTests(unittest.TestCase):
    def test_fresh_runtime_runs_recovery_and_keeps_robot_stopped(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(Path(temp) / "terminal.db")
            try:
                state = runtime.store.get_robot_runtime_state(ACCOUNT_ID)
                self.assertIsNotNone(state)
                self.assertEqual(state.mode, "ROBOT_STOPPED")
                self.assertEqual(state.recovery_status, "ROBOT_STOPPED")
                self.assertFalse(runtime.robot_admission_ready())
            finally:
                runtime.close()

    def test_running_open_trade_recovers_to_ready_without_geometry_read(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "terminal.db"
            runtime = _runtime(path)
            try:
                _set_running(runtime)
                candidate, created = runtime.store.create_robot_candidate(
                    candidate_id="candidate-open",
                    trading_account_id=ACCOUNT_ID,
                    symbol=Symbol("TESTUSDT"),
                    status="APPROVED",
                    signal_snapshot=_snapshot(),
                    approved_at_ms=1002,
                    updated_at_ms=1002,
                )
                self.assertTrue(created)
                _, trade_created = runtime.store.create_robot_trade(
                    trade_id="trade-open",
                    trading_account_id=ACCOUNT_ID,
                    candidate_id=candidate.candidate_id,
                    symbol=Symbol("TESTUSDT"),
                    direction="LONG",
                    pattern="Falling Wedge",
                    source_timeframe="1",
                    signal_time_ms=10,
                    entry_time_ms=20,
                    entry_path="MARKET",
                    actual_wv=Decimal("1"),
                    average_entry=Decimal("100"),
                    stop_price=Decimal("98"),
                    take_price=Decimal("103"),
                    created_at_ms=1003,
                )
                self.assertTrue(trade_created)
            finally:
                runtime.close()

            restarted = _runtime(path)
            try:
                state = restarted.store.get_robot_runtime_state(ACCOUNT_ID)
                self.assertEqual(state.recovery_status, "READY")
                self.assertTrue(restarted.robot_admission_ready())
            finally:
                restarted.close()

    def test_legacy_waiting_candidate_without_cursor_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "terminal.db"
            runtime = _runtime(path)
            try:
                candidate, created = runtime.store.create_robot_candidate(
                    candidate_id="candidate-waiting",
                    trading_account_id=ACCOUNT_ID,
                    symbol=Symbol("TESTUSDT"),
                    status="APPROVED",
                    signal_snapshot=_snapshot(),
                    approved_at_ms=1000,
                    updated_at_ms=1000,
                )
                self.assertTrue(created)
                runtime.store.save_robot_candidate_state(
                    candidate.candidate_id,
                    status="APPROVED",
                    robot_state=_robot_state(),
                    expected_revision=candidate.state_revision,
                    updated_at_ms=1001,
                )
                _set_running(runtime)
            finally:
                runtime.close()

            restarted = _runtime(path)
            try:
                state = restarted.store.get_robot_runtime_state(ACCOUNT_ID)
                self.assertEqual(state.recovery_status, "RECONCILIATION_REQUIRED")
                self.assertFalse(restarted.robot_admission_ready())
                self.assertIn("Scanner geometry cursor anchor", state.reason)
            finally:
                restarted.close()

    def test_injected_authoritative_geometry_provider_restores_waiting_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "terminal.db"
            runtime = _runtime(path)
            try:
                candidate, created = runtime.store.create_robot_candidate(
                    candidate_id="candidate-waiting",
                    trading_account_id=ACCOUNT_ID,
                    symbol=Symbol("TESTUSDT"),
                    status="APPROVED",
                    signal_snapshot=_snapshot(),
                    approved_at_ms=1000,
                    updated_at_ms=1000,
                )
                self.assertTrue(created)
                runtime.store.save_robot_candidate_state(
                    candidate.candidate_id,
                    status="APPROVED",
                    robot_state=_robot_state(),
                    expected_revision=candidate.state_revision,
                    updated_at_ms=1001,
                )
                _set_running(runtime)
            finally:
                runtime.close()

            restarted = _runtime(
                path,
                latest_geometry_index_provider=lambda symbol, snapshot: 105,
            )
            try:
                state = restarted.store.get_robot_runtime_state(ACCOUNT_ID)
                self.assertEqual(state.recovery_status, "READY")
                self.assertTrue(restarted.robot_admission_ready())
                recovered = restarted.store.get_robot_candidate("candidate-waiting")
                self.assertEqual(recovered.robot_state["geometry_cursor"], 105)
            finally:
                restarted.close()


if __name__ == "__main__":
    unittest.main()
