"""Regression for the production geometry-provider bypass of candle warm-up."""
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from terminal.domain.models import Symbol
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.paper_http_server import BackendRuntimeIntentPorts, SerializedPaperRuntime
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import (
    StaticBookProvider, _instrument, _seed_candidate, _set_admission,
)
from tests.test_robot_breakout_monitor import _snapshot, T0_MS

SYMBOLS = ("2ZUSDT", "ARBUSDT", "ARKUSDT")
CANDLE = {"time_ms": T0_MS + 60_000, "high": 100., "low": 99., "close": 100.}


def make_runtime(path, cache):
    instrument = _instrument()
    runtime = PaperRuntime(
        path, book_provider=StaticBookProvider(), instrument_snapshot=instrument,
        instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
        robot_closed_candle_provider=cache,
        # Deliberately do NOT inject a geometry provider: the old tests did,
        # hiding the production bypass responsible for the 9-second stall.
    )
    for symbol in SYMBOLS:
        _seed_candidate(runtime, "candidate-" + symbol, symbol,
                        snapshot=_snapshot(symbol=symbol), state={
                            "phase": "RETEST_DETECTED", "direction": "LONG",
                            "pattern": "Falling Wedge",
                            "geometry_cursor": 100, "breakout_index": 99,
                            "retest_index": 100, "last_event": "RETEST",
                            "state_version": "1.0",
                        })
    _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
    return runtime


class RecoveryIngressTests(unittest.TestCase):
    def test_default_geometry_recovery_uses_warmed_evidence_without_rest(self):
        calls = []
        cache = CachedClosedCandleProvider(lambda symbol: calls.append(threading.get_ident()) or CANDLE)
        with tempfile.TemporaryDirectory() as temp:
            owner = SerializedPaperRuntime(lambda: make_runtime(Path(temp) / "paper.sqlite3", cache))
            try:
                owner.warm_robot_closed_candles()
                with patch("scanner_geometry_cursor.latest_scanner_closed_candle_time_ms",
                           side_effect=AssertionError("REST on serialized owner")) as rest:
                    result = owner.call(lambda runtime: runtime.robot_reconcile())
                self.assertTrue(result.success, result.reason)
                self.assertEqual(result.recovery_status, "PAUSED")
                self.assertEqual(result.unresolved_candidate_ids, ())
                rest.assert_not_called()
                self.assertEqual(len(calls), 3)
                self.assertNotIn(owner._thread.ident, calls)
            finally:
                owner.close()

    def test_missing_or_stale_geometry_evidence_fails_closed_without_fetch(self):
        for stale in (False, True):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as temp:
                now = [0.]
                calls = []
                cache = CachedClosedCandleProvider(lambda symbol: calls.append(symbol) or CANDLE,
                                                  clock=lambda: now[0], max_age_s=1)
                owner = SerializedPaperRuntime(lambda: make_runtime(Path(temp) / "paper.sqlite3", cache))
                try:
                    if stale:
                        owner.warm_robot_closed_candles()
                        now[0] = 2.
                    before = len(calls)
                    result = owner.call(lambda runtime: runtime.robot_reconcile())
                    self.assertFalse(result.success)
                    self.assertEqual(result.recovery_status, "RECONCILIATION_REQUIRED")
                    self.assertIn("cache unavailable", result.reason)
                    self.assertEqual(len(calls), before)
                finally:
                    owner.close()

    def test_slow_preparation_does_not_starve_ordered_multi_symbol_ingress(self):
        fetching, release = threading.Event(), threading.Event()
        def fetch(symbol):
            fetching.set()
            if not release.wait(5):
                raise AssertionError("test did not release network preparation")
            return CANDLE
        cache = CachedClosedCandleProvider(fetch)
        with tempfile.TemporaryDirectory() as temp:
            owner = SerializedPaperRuntime(lambda: make_runtime(Path(temp) / "paper.sqlite3", cache))
            warmer = threading.Thread(target=owner.warm_robot_closed_candles)
            try:
                roles = owner.call(lambda runtime: runtime.robot_protection_coverage_roles())
                self.assertEqual(roles, dict.fromkeys(SYMBOLS, "ENTRY_PENDING"))
                warmer.start()
                self.assertTrue(fetching.wait(2))
                observed = []
                # 96 events during blocked REST would exceed the old capacity 64
                # when recovery fetches on the owner. Bound each delivered batch
                # deterministically; no sleeps or machine-speed assertions.
                for offset in range(0, 96, 16):
                    for index in range(offset, offset + 16):
                        symbol = SYMBOLS[index % 3]
                        def event(runtime, index=index, symbol=symbol):
                            book = StaticBookProvider().get_book(Symbol(symbol))
                            runtime.process_robot_market_event(symbol, book,
                                event_id=f"burst:{index}", received_at_ms=book.received_at_ms)
                            observed.append(index)
                        owner.enqueue(event, symbol=symbol, coverage_role=roles[symbol])
                    owner.call(lambda runtime: None, timeout=2)
                self.assertEqual(observed, list(range(96)))
                self.assertEqual(owner.protection_ingress_metrics()["current_pending"], 0)
                self.assertLessEqual(owner.protection_ingress_metrics()["high_watermark"], 16)
                release.set()
                warmer.join(5)
                self.assertFalse(warmer.is_alive())
                with patch("scanner_geometry_cursor.latest_scanner_closed_candle_time_ms",
                           side_effect=AssertionError("recovery bypassed cache")):
                    result = owner.call(lambda runtime: runtime.robot_reconcile())
                self.assertTrue(result.success, result.reason)
            finally:
                release.set()
                if warmer.ident is not None:
                    warmer.join(5)
                owner.close()

    def test_start_boundary_warms_before_owner_recovery(self):
        calls = []
        class Runtime:
            def warm_robot_closed_candles(self): calls.append("warm")
            def call(self, operation):
                calls.append("owner")
                return operation(self)
            def robot_start(self): calls.append("start")
        BackendRuntimeIntentPorts(Runtime(), object(), operator_token="").start_robot()
        self.assertEqual(calls, ["warm", "owner", "start"])
