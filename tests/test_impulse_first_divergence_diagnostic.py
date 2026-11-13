"""A diagnostic signal must share the native runner's exclusive end boundary."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from research.simulator_v2.diagnose_first_divergence import eligible_trace_signal


class FirstDivergenceDiagnosticBoundaryTests(unittest.TestCase):
    def test_only_preterminal_signals_are_traced(self):
        end_exclusive_ms = 1794355200000  # 2026-11-11 00:00 UTC
        self.assertFalse(eligible_trace_signal(None, end_exclusive_ms=end_exclusive_ms))
        self.assertTrue(eligible_trace_signal(
            SimpleNamespace(known_at_ms=end_exclusive_ms - 60_000),
            end_exclusive_ms=end_exclusive_ms,
        ))
        self.assertFalse(eligible_trace_signal(
            SimpleNamespace(known_at_ms=end_exclusive_ms),
            end_exclusive_ms=end_exclusive_ms,
        ))
        self.assertFalse(eligible_trace_signal(
            SimpleNamespace(known_at_ms=end_exclusive_ms + 60_000),
            end_exclusive_ms=end_exclusive_ms,
        ))


if __name__ == "__main__":
    unittest.main()
