"""The *real* Robot coordinator runs only inside disposable SIMULATION scope."""
import unittest
from decimal import Decimal as D

from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.robot_sandbox import (
    IsolatedSimulationRobot, SimulationExecutionNotConnected, _BlockedExecutionPort,
)
from terminal.domain.models import TradingAccountId


def minute(index, close="100"):
    c = D(close)
    return Candle(
        start_ms=index * 60_000, interval_ms=60_000,
        open=c, high=c + 1, low=c - 1, close=c, volume=D("1"),
    )


class NativeRobotSandboxTests(unittest.TestCase):
    def test_independent_accounts_real_monitor_no_external_execution(self):
        first = VirtualReplaySession(
            simulation_run_id="first-run", symbol="BTCUSDT",
            initial_balance=D("1000"),
        )
        second = VirtualReplaySession(
            simulation_run_id="second-run", symbol="BTCUSDT",
            initial_balance=D("500"),
        )
        with IsolatedSimulationRobot(first, tick_size=D("0.01")) as a:
            with IsolatedSimulationRobot(second, tick_size=D("0.01")) as b:
                self.assertEqual(a.account_id.value, "simulation:first-run")
                self.assertNotEqual(a.account_id, TradingAccountId("paper"))
                self.assertNotEqual(a.account_id, b.account_id)
                self.assertNotEqual(a._store_path, b._store_path)
                self.assertIsNone(a._store.get_robot_runtime_state(b.account_id))
                self.assertIsNone(b._store.get_robot_runtime_state(a.account_id))
                self.assertEqual(a._store.get_robot_runtime_state(a.account_id).mode,
                                 "ROBOT_STOPPED")
                self.assertIsNone(a.closed_m1_for_robot("BTCUSDT"))
                with self.assertRaisesRegex(RuntimeError, "no completed M1"):
                    a.tick()
                first.step(minute(0))
                second.step(minute(0, "80"))
                self.assertEqual(a.virtual_clock_ms(), 60_000)
                self.assertEqual(a.closed_m1_for_robot("BTCUSDT")["close"], 100.)
                self.assertEqual(b.closed_m1_for_robot("BTCUSDT")["close"], 80.)
                self.assertEqual(a.tick(), ())
                self.assertEqual(b.tick(), ())
                self.assertEqual(first.account.fills, ())
                self.assertEqual(second.account.fills, ())
                self.assertEqual(a._store.get_robot_runtime_state(a.account_id).mode,
                                 "ROBOT_STOPPED")
                with self.assertRaisesRegex(ValueError, "cross-symbol"):
                    a.closed_m1_for_robot("ETHUSDT")
                with self.assertRaises(SimulationExecutionNotConnected):
                    _BlockedExecutionPort().create_limit(object())
        with self.assertRaisesRegex(RuntimeError, "closed"):
            a.tick()

    def test_invalid_or_duplicate_robot_is_not_connected(self):
        with self.assertRaises(ValueError):
            IsolatedSimulationRobot(
                VirtualReplaySession(
                    simulation_run_id="invalid", symbol="BTCUSDT",
                    initial_balance=D("100"),
                ), tick_size=D("0"),
            )
        self.assertEqual(
            [name for name in (
                "create_limit", "amend_limit", "cancel_limit", "create_stop",
                "amend_stop", "create_take", "amend_take", "full_close",
            ) if callable(getattr(_BlockedExecutionPort, name, None))],
            ["create_limit", "amend_limit", "cancel_limit", "create_stop",
             "amend_stop", "create_take", "amend_take", "full_close"],
        )


if __name__ == "__main__":
    unittest.main()
