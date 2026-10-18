"""A proven coverage-loss fence must not be lost to missing closed-candle evidence.

Incident 2026-10-18 16:18 UTC: a websocket disconnect fenced Robot admission and
three open positions were emergency-closed. The proven recovery then released the
fence through ``robot_reconcile`` on the owner thread, which reads every APPROVED
candidate's latest closed candle from the cache and never fetches. SENTUSDT had been
approved ~80 s earlier and its candle had not been cached yet, so reconciliation
raised "closed candle cache unavailable", overwrote the fence's durable reason and
left Robot in RECONCILIATION_REQUIRED, blocking all PAPER_AUTO entries.

The release is now deferred (fence and reason untouched, admission closed) until the
coverage thread has warmed the evidence off the owner thread, then retried. Real
emergency closes, an unhealthy ingress and independent reconciliation causes are
unchanged. All databases are temporary; there is no network.
"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from robot_state_machine import initialize_state
from scanner_geometry_cursor import CURSOR_VERSION
from terminal.domain.models import Symbol
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.paper_http_server import (
    DEFERRED_RELEASE_RETRY_INTERVAL_S,
    RobotProtectionCoverageManager,
)
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_continuity_recovery_candidate_snapshot import (
    ACCOUNT,
    _box_instrument,
    _footprint,
    _recover,
    _seed_box_with_four_entry_limits,
    _status,
)
from tests.test_terminal_paper_runtime import StaticBookProvider, _instrument, _set_admission

SYMBOL = "BTCUSDT"
LOSS = "websocket_disconnect:SSLError"
HEALTHY = lambda: True  # noqa: E731
APPROVED_SYMBOL = "SENTUSDT"
SOURCE_TIME_MS = 1_792_340_000_000  # minute aligned
FENCE_PREFIX = "ROBOT_PROTECTION_COVERAGE_LOST symbol=BTCUSDT"


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class _CountingFetch:
    def __init__(self):
        self.calls = []

    def __call__(self, symbol):
        self.calls.append((symbol, threading.current_thread().name))
        return {"time_ms": SOURCE_TIME_MS + 60_000, "high": 1.0, "low": 1.0}


def _wedge_snapshot():
    return {
        "symbol": APPROVED_SYMBOL,
        "pattern": "Falling Wedge",
        "scanner_geometry_cursor": {
            "version": CURSOR_VERSION, "timeframe": "1", "geometry_index": 100,
            "source_candle_time_ms": SOURCE_TIME_MS,
        },
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 400, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
    }


def _state(runtime):
    state = runtime.store.get_robot_runtime_state(ACCOUNT)
    return state.mode, state.recovery_status, state.reason


class ContinuityReleaseCandleEvidenceTests(unittest.TestCase):
    def _runtime(self, temp, cache):
        runtime = PaperRuntime(
            Path(temp) / "paper.sqlite3",
            book_provider=StaticBookProvider(),
            instrument_snapshot=_instrument(),
            instrument_provider=_box_instrument,
            robot_closed_candle_provider=cache,
        )
        _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        return runtime

    def _fenced_and_recovered(self, temp, *, with_approved_candidate=True):
        self.clock, self.fetch = _Clock(), _CountingFetch()
        self.cache = CachedClosedCandleProvider(self.fetch, clock=self.clock, max_age_s=90.0)
        runtime = self._runtime(temp, self.cache)
        _seed_box_with_four_entry_limits(runtime)
        if with_approved_candidate:
            candidate, _ = runtime.store.create_robot_candidate(
                candidate_id="approved-sent", trading_account_id=ACCOUNT,
                symbol=Symbol(APPROVED_SYMBOL),
                status="APPROVED", signal_snapshot=_wedge_snapshot(),
                approved_at_ms=2_000, updated_at_ms=2_000,
            )
            state, _ = initialize_state({
                "candidate_id": candidate.candidate_id, "status": "APPROVED", "timeframe": "1",
                "symbol": APPROVED_SYMBOL, "signal_snapshot": _wedge_snapshot(),
            })
            runtime.store.save_robot_candidate_state(
                candidate.candidate_id, status="APPROVED", robot_state=state,
                expected_revision=candidate.state_revision, updated_at_ms=2_001,
            )
        self.assertTrue(runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS))
        self.assertTrue(_recover(runtime))
        self.assertEqual(_state(runtime)[:2], ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
        return runtime

    # --- the incident ------------------------------------------------------
    def test_missing_candle_evidence_defers_release_and_keeps_the_fence_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._fenced_and_recovered(temp)
            try:
                fence_state = _state(runtime)
                self.assertTrue(fence_state[2].startswith(FENCE_PREFIX))
                self.assertFalse(runtime.robot_recovery_evidence_ready())
                released = runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY)
                self.assertFalse(released)
                # Fence untouched: same durable version and reason, admission closed.
                self.assertEqual(_state(runtime), fence_state)
                self.assertNotIn("cache unavailable", _state(runtime)[2])
                self.assertFalse(runtime.robot_admission_ready())
                self.assertTrue(runtime.robot_continuity_release_deferred())
                # The owner thread never fetched anything.
                self.assertEqual(self.fetch.calls, [])
            finally:
                runtime.close()

    def test_release_succeeds_after_evidence_is_warmed_off_the_owner_thread(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._fenced_and_recovered(temp)
            try:
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY))
                worker = threading.Thread(
                    target=self.cache.warm, args=([APPROVED_SYMBOL],), name="coverage-thread")
                worker.start()
                worker.join()
                self.assertEqual(self.fetch.calls, [(APPROVED_SYMBOL, "robot-candle-warm_0")])
                before = _footprint(runtime)
                self.assertTrue(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "READY", None))
                self.assertFalse(runtime.robot_continuity_release_deferred())
                self.assertEqual(_footprint(runtime), before)
                self.assertEqual(len(self.fetch.calls), 1)
            finally:
                runtime.close()

    def test_stale_evidence_counts_as_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._fenced_and_recovered(temp)
            try:
                self.cache.warm([APPROVED_SYMBOL])
                self.assertTrue(runtime.robot_recovery_evidence_ready())
                self.clock.now += 91.0
                self.assertFalse(runtime.robot_recovery_evidence_ready())
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY))
                self.assertTrue(_state(runtime)[2].startswith(FENCE_PREFIX))
            finally:
                runtime.close()

    # --- what must not change ---------------------------------------------
    def test_recovery_and_emergency_exits_do_not_wait_for_candle_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            self.clock, self.fetch = _Clock(), _CountingFetch()
            self.cache = CachedClosedCandleProvider(self.fetch, clock=self.clock)
            runtime = self._runtime(temp, self.cache)
            try:
                _candidate, order_ids = _seed_box_with_four_entry_limits(runtime)
                self.assertTrue(runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS))
                self.assertTrue(_recover(runtime))  # cache is empty
                self.assertEqual([_status(runtime, o) for o in order_ids], ["cancelled"] * 4)
                self.assertEqual(self.fetch.calls, [])
            finally:
                runtime.close()

    def test_unhealthy_ingress_still_holds_the_fence_even_with_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._fenced_and_recovered(temp)
            try:
                self.cache.warm([APPROVED_SYMBOL])
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=lambda: False))
                self.assertTrue(_state(runtime)[2].startswith(FENCE_PREFIX))
                self.assertFalse(runtime.robot_continuity_release_deferred())
            finally:
                runtime.close()

    def test_no_approved_candidate_needing_evidence_releases_immediately(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._fenced_and_recovered(temp, with_approved_candidate=False)
            try:
                self.assertTrue(runtime.robot_recovery_evidence_ready())
                self.assertTrue(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "READY", None))
            finally:
                runtime.close()

    def test_a_genuine_recovery_failure_still_fails_closed(self):
        """Evidence present but unusable is not hidden by the deferral."""
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._fenced_and_recovered(temp)
            try:
                self.cache.warm([APPROVED_SYMBOL])
                with patch.object(runtime, "_robot_latest_geometry_index",
                                  side_effect=RuntimeError("geometry unprovable")), \
                        patch.object(runtime._robot_recovery, "_latest_geometry_index_provider",
                                     side_effect=RuntimeError("geometry unprovable")):
                    self.assertFalse(runtime.release_robot_protection_continuity_fence(
                        SYMBOL, ingress_healthy=HEALTHY))
                self.assertEqual(_state(runtime)[:2], ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
                self.assertFalse(runtime.robot_admission_ready())
            finally:
                runtime.close()


class _FakeOwner:
    def __init__(self, deferred_sequence):
        self.deferred_sequence = list(deferred_sequence)
        self.releases = []

    def release_robot_protection_continuity_fence(self, symbol, *, ingress_healthy):
        self.releases.append(symbol)
        return False

    def robot_continuity_release_deferred(self):
        return self.deferred_sequence.pop(0) if self.deferred_sequence else False


class _FakeSerialized:
    def __init__(self, owner, *, warm_error=None):
        self.owner, self.warm_calls, self.warm_error = owner, 0, warm_error
        self.threads = []

    def call(self, fn):
        return fn(self.owner)

    def warm_robot_closed_candles(self):
        self.warm_calls += 1
        self.threads.append(threading.current_thread().name)
        if self.warm_error:
            raise self.warm_error


class DeferredReleaseRetryTests(unittest.TestCase):
    def _manager(self, runtime):
        return RobotProtectionCoverageManager(object(), runtime, recovery_session=object())

    def test_deferral_is_tracked_and_cleared_by_the_owner_release_result(self):
        owner = _FakeOwner([True, False])
        runtime = _FakeSerialized(owner)
        manager = self._manager(runtime)
        manager._release_continuity_fence(owner, "BTCUSDT")
        self.assertEqual(manager._release_retry, {"BTCUSDT"})
        manager._release_continuity_fence(owner, "BTCUSDT")
        self.assertEqual(manager._release_retry, set())

    def test_retry_warms_off_owner_then_releases_and_stops_when_released(self):
        owner = _FakeOwner([True, False])  # first release re-defers nothing after retry
        runtime = _FakeSerialized(owner)
        manager = self._manager(runtime)
        manager._release_continuity_fence(owner, "BTCUSDT")  # deferred -> pending
        with patch("terminal.runtime.paper_http_server.time.monotonic", return_value=500.0):
            manager._retry_deferred_fence_releases()
        self.assertEqual(runtime.warm_calls, 1)
        self.assertEqual(owner.releases, ["BTCUSDT", "BTCUSDT"])
        self.assertEqual(manager._release_retry, set())
        with patch("terminal.runtime.paper_http_server.time.monotonic", return_value=900.0):
            manager._retry_deferred_fence_releases()  # nothing pending
        self.assertEqual(runtime.warm_calls, 1)

    def test_retries_are_rate_limited_while_evidence_stays_unavailable(self):
        owner = _FakeOwner([True] * 10)
        runtime = _FakeSerialized(owner)
        manager = self._manager(runtime)
        manager._release_continuity_fence(owner, "BTCUSDT")
        with patch("terminal.runtime.paper_http_server.time.monotonic", return_value=100.0):
            manager._retry_deferred_fence_releases()
            manager._retry_deferred_fence_releases()
        self.assertEqual(runtime.warm_calls, 1)
        with patch("terminal.runtime.paper_http_server.time.monotonic",
                   return_value=100.0 + DEFERRED_RELEASE_RETRY_INTERVAL_S + 1):
            manager._retry_deferred_fence_releases()
        self.assertEqual(runtime.warm_calls, 2)
        self.assertEqual(manager._release_retry, {"BTCUSDT"})  # still fenced, still retrying

    def test_warm_failure_does_not_stop_the_retry_or_unfence_anything(self):
        owner = _FakeOwner([True, True])
        runtime = _FakeSerialized(owner, warm_error=RuntimeError("bybit down"))
        manager = self._manager(runtime)
        manager._release_continuity_fence(owner, "BTCUSDT")
        with patch("terminal.runtime.paper_http_server.time.monotonic", return_value=500.0):
            manager._retry_deferred_fence_releases()
        self.assertEqual(owner.releases, ["BTCUSDT", "BTCUSDT"])
        self.assertEqual(manager._release_retry, {"BTCUSDT"})


if __name__ == "__main__":
    unittest.main()
