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

import subprocess
import sys
import time


SCENARIOS = (
    "tests.test_robot_breakout_monitor.RobotBreakoutMonitorTests."
    "test_full_limit_fill_creates_protected_trade",
    "tests.test_robot_paper_execution_threading.RobotPaperExecutionThreadingTests."
    "test_a_b_c_d_f_real_topology_limit_fill_and_protection_dispatch_to_owner_thread",
    "tests.test_robot_paper_execution_threading.RobotPaperExecutionThreadingTests."
    "test_g_restart_with_stale_retest_detected_creates_exactly_one_order",
)


def run() -> int:
    started = time.monotonic()
    command = [sys.executable, "-m", "unittest", "-v", *SCENARIOS]
    completed = subprocess.run(command, check=False)
    elapsed = time.monotonic() - started
    status = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"ROBOT_PAPER_ACCEPTANCE {status} scenarios={len(SCENARIOS)} elapsed_s={elapsed:.2f}")
    return completed.returncode


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
