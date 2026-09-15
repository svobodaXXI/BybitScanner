"""Run the deterministic Robot v0.1 PAPER acceptance gate.

This is deliberately smaller than the full regression suite and deliberately
independent of live market timing. It composes existing production-path
regressions that prove the two halves of the entry lifecycle:

1. closed-candle breakout -> retest -> LIMIT -> fill -> protected trade;
2. real SerializedPaperRuntime topology -> real PAPER execution/guard/store
   path -> resting LIMIT fill -> STOP/TAKE -> durable OPEN candidate/trade.

The first scenario controls only candle/fill inputs. The second uses the real
PaperRuntime execution stack and a deterministic in-memory-style book provider.
No Bybit network access, real credentials, or user runtime database is used.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import types
import unittest


SCENARIOS = (
    "tests.test_robot_breakout_monitor.RobotBreakoutMonitorTests."
    "test_full_limit_fill_creates_protected_trade",
    "tests.test_robot_paper_execution_threading.RobotPaperExecutionThreadingTests."
    "test_a_b_c_d_f_real_topology_limit_fill_and_protection_dispatch_to_owner_thread",
    "tests.test_robot_paper_execution_threading.RobotPaperExecutionThreadingTests."
    "test_g_restart_with_stale_retest_detected_creates_exactly_one_order",
)


def _ensure_test_config() -> None:
    """Provide a non-secret import stub only when machine-local config is absent.

    ``config.py`` is intentionally gitignored because a developer/runtime copy
    contains local Telegram and Scanner settings. The deterministic acceptance
    scenarios do not exercise Scanner networking or Telegram delivery, but the
    production PaperRuntime import graph reaches ``main.py`` and therefore must
    be able to import that module in a clean GitHub Actions checkout.

    Never replace a real config module. The stub exists only in this process and
    returns ``None`` for settings irrelevant to these PAPER-only scenarios.
    """
    if "config" in sys.modules or importlib.util.find_spec("config") is not None:
        return
    stub = types.ModuleType("config")
    stub.MODE = "hunter"
    stub.MIN_SCORE = 60
    stub.MAX_SYMBOLS = None
    stub.__getattr__ = lambda _name: None
    sys.modules["config"] = stub


def _load_suite(loader: unittest.TestLoader | None = None) -> unittest.TestSuite:
    active_loader = loader or unittest.TestLoader()
    suite = unittest.TestSuite()
    for scenario in SCENARIOS:
        suite.addTests(active_loader.loadTestsFromName(scenario))
    return suite


def run() -> int:
    started = time.monotonic()
    _ensure_test_config()
    result = unittest.TextTestRunner(verbosity=2).run(_load_suite())
    elapsed = time.monotonic() - started
    status = "PASS" if result.wasSuccessful() else "FAIL"
    print(f"ROBOT_PAPER_ACCEPTANCE {status} scenarios={len(SCENARIOS)} elapsed_s={elapsed:.2f}")
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
