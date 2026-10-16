"""MDC-DIAG-1: durable evidence of the first protection continuity fence.

The first transition into RECONCILIATION_REQUIRED keeps its cause (reason, source
generation, event, ingress snapshot) and an EMERGENCY_CLOSE incident links back to
it. Diagnostics are best-effort: no failure, full queue or odd evidence changes the
fence, the recovery, the release or the protection lifecycle.
"""

import threading
import time
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from robot_failure_diagnostics import load_recent_robot_incidents, record_robot_incident
from terminal.runtime import paper_runtime
from terminal.runtime.paper_http_server import (
    RobotProtectionCoverageManager, _fence_with_evidence,
)
from tests import test_robot_paper_acceptance as acceptance
from tests.test_continuity_recovery_candidate_snapshot import (
    ACCOUNT, _recover, _runtime, _seed_box_with_four_entry_limits,
)

SYMBOL = "BTCUSDT"
LOSS = "websocket_disconnect:SSLError"
HEALTHY = lambda: True  # noqa: E731
FEED_GAP = "test_protection_feed_gap_emergency_closes_owned_trade_on_fresh_snapshot"


def _state(runtime):
    state = runtime.store.get_robot_runtime_state(ACCOUNT)
    return state.mode, state.recovery_status, state.reason, state.version


class FirstFenceEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.runtime = _runtime(temp.name)
        self.addCleanup(self.runtime.close)
        self.writes = []
        self.runtime._diagnostic_submit = self.writes.append
        _seed_box_with_four_entry_limits(self.runtime)

    def test_first_fence_keeps_cause_generation_event_and_ingress(self):
        self.runtime.note_continuity_evidence(SYMBOL, {
            "source_generation": 1, "event_id": "BTCUSDT:7:9", "coverage_role": "OPEN",
            "ingress_current_pending": 3, "ingress_max_queue_latency_ms": 12.5,
            "nested": {"dropped": True},
        })
        self.assertTrue(self.runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS))
        mode, status, reason, version = _state(self.runtime)
        self.assertEqual((mode, status), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
        self.assertEqual(reason, f"ROBOT_PROTECTION_COVERAGE_LOST symbol={SYMBOL} reason={LOSS}")
        record = self.runtime._continuity_fence_evidence
        self.assertEqual(record["fence_id"], f"continuity-fence-{version}")
        self.assertEqual(record["fence_version"], version)
        self.assertEqual((record["fence_symbol"], record["continuity_reason"]), (SYMBOL, LOSS))
        self.assertEqual(record["prior_recovery_status"], "READY")
        self.assertEqual((record["source_generation"], record["event_id"]), (1, "BTCUSDT:7:9"))
        self.assertEqual(record["ingress_current_pending"], 3)
        self.assertNotIn("nested", record)  # only bounded scalars are kept
        self.assertTrue(record["fenced_at_utc"].endswith("Z"))
        self.assertEqual(len(self.writes), 1)
        # The queued write produces one sanitized durable incident.
        self.writes[0]()
        incidents = load_recent_robot_incidents(incident_dir=self.root / "robot_incidents")
        fence = [i for i in incidents if i["incident_type"] == "ROBOT_PROTECTION_CONTINUITY_FENCE"]
        self.assertEqual(len(fence), 1)
        self.assertEqual(fence[0]["reason_code"], "MARKET_DATA_CONTINUITY_FENCE")
        self.assertEqual(fence[0]["facts"]["continuity_reason"], LOSS)
        self.assertEqual(fence[0]["facts"]["source_generation"], 1)
        self.assertEqual(fence[0]["facts"]["fence_id"], record["fence_id"])

    def test_repeated_fence_never_overwrites_the_origin(self):
        self.runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS)
        first, before = dict(self.runtime._continuity_fence_evidence), _state(self.runtime)
        self.runtime.note_continuity_evidence("ETHUSDT", {"source_generation": 5})
        self.assertTrue(self.runtime.fence_robot_protection_continuity_loss("ETHUSDT", "ingress_overflow"))
        self.assertTrue(self.runtime.fence_robot_protection_continuity_loss(SYMBOL, "event_identity_mismatch"))
        self.assertEqual(self.runtime._continuity_fence_evidence, first)
        self.assertEqual(_state(self.runtime), before)  # durable fence untouched, as before
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.runtime.__dict__.get("_continuity_evidence_pending"), {})

    def test_release_clears_the_record_and_the_next_fence_records_its_own_cause(self):
        self.runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS)
        self.assertTrue(_recover(self.runtime))
        self.assertTrue(self.runtime.release_robot_protection_continuity_fence(
            SYMBOL, ingress_healthy=HEALTHY))
        self.assertIsNone(self.runtime._continuity_fence_evidence)
        self.runtime.fence_robot_protection_continuity_loss(SYMBOL, "subscribe_failed")
        record = self.runtime._continuity_fence_evidence
        self.assertEqual(record["continuity_reason"], "subscribe_failed")
        self.assertEqual(record["fence_version"], _state(self.runtime)[3])
        self.assertEqual(len(self.writes), 2)

    def test_diagnostic_failures_never_change_fence_recovery_or_release(self):
        def broken_submit(_write):
            raise OSError("disk unavailable")

        self.runtime._diagnostic_submit = broken_submit
        self.runtime.note_continuity_evidence(SYMBOL, 5)  # not a mapping: ignored
        self.assertTrue(self.runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS))
        self.assertEqual(_state(self.runtime)[1], "RECONCILIATION_REQUIRED")
        self.assertIn(SYMBOL, self.runtime._continuity_fence_origin)
        self.assertTrue(_recover(self.runtime))
        self.assertTrue(self.runtime.release_robot_protection_continuity_fence(
            SYMBOL, ingress_healthy=HEALTHY))
        self.assertEqual(_state(self.runtime)[1], "READY")

    def test_link_facts_survive_a_missing_or_corrupt_record(self):
        book = SimpleNamespace(source_generation=2)
        self.runtime._continuity_fence_evidence = "corrupt"
        link = self.runtime._continuity_fence_link(LOSS, "BTCUSDT:1:1", book)
        self.assertIsNone(link["continuity_fence_id"])
        self.assertEqual((link["recovery_reason"], link["recovery_source_generation"]), (LOSS, 2))


class DiagnosticsWriterTests(unittest.TestCase):
    def test_full_queue_or_failing_write_never_blocks_or_raises(self):
        writer = paper_runtime._BestEffortDiagnosticsWriter(limit=1)
        gate, done = threading.Event(), threading.Event()
        self.assertTrue(writer.submit(lambda: gate.wait(5)))  # occupies the thread
        time.sleep(0.05)
        self.assertTrue(writer.submit(lambda: None))  # fills the queue
        started = time.perf_counter()
        self.assertFalse(writer.submit(lambda: None))  # full: dropped, not waited for
        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertEqual(writer.dropped, 1)
        def drained():
            deadline = time.monotonic() + 5
            while not writer._queue.empty() and time.monotonic() < deadline:
                time.sleep(0.01)  # the thread takes the queued write

        def fail():
            raise OSError("write failed")

        gate.set()
        drained()
        self.assertTrue(writer.submit(fail))
        drained()
        self.assertTrue(writer.submit(done.set))
        self.assertTrue(done.wait(5))  # the thread survives a failing write
        self.assertEqual(writer.dropped, 2)


class CoverageEvidenceTests(unittest.TestCase):
    def test_fence_call_is_unchanged_whatever_the_diagnostics_do(self):
        calls = []

        class Plain:  # existing runtimes and fakes without the diagnostics hook
            def fence_robot_protection_continuity_loss(self, symbol, reason):
                calls.append((symbol, reason))
                return True

        class Broken(Plain):
            def note_continuity_evidence(self, symbol, evidence):
                raise RuntimeError("diagnostics broken")

        for runtime in (Plain(), Broken()):
            self.assertTrue(_fence_with_evidence(runtime, SYMBOL, LOSS, {"source_generation": 1}))
        self.assertTrue(_fence_with_evidence(Plain(), SYMBOL, LOSS, None))
        self.assertEqual(calls, [(SYMBOL, LOSS)] * 3)

    def test_ingress_snapshot_is_best_effort(self):
        class Metrics:
            def protection_ingress_metrics(self):
                return {"current_pending": 4, "high_watermark": 9, "last_overflow_symbol": "X"}

        class NoMetrics:
            def protection_ingress_metrics(self):
                raise RuntimeError("owner unavailable")

        ok = RobotProtectionCoverageManager._continuity_evidence(
            SimpleNamespace(_runtime=Metrics()), SYMBOL, source_generation=2, event_id=None)
        self.assertEqual((ok["source_generation"], ok["ingress_current_pending"]), (2, 4))
        self.assertEqual(ok["ingress_last_overflow_symbol"], "X")
        self.assertNotIn("event_id", ok)
        missing = RobotProtectionCoverageManager._continuity_evidence(
            SimpleNamespace(_runtime=NoMetrics()), SYMBOL)
        self.assertEqual(missing["ingress_metrics"], "UNAVAILABLE")
        odd = RobotProtectionCoverageManager._continuity_evidence(
            SimpleNamespace(_runtime=SimpleNamespace(protection_ingress_metrics=lambda: None)),
            SYMBOL)
        self.assertEqual(odd["ingress_metrics"], "UNAVAILABLE")
        self.assertEqual(RobotProtectionCoverageManager._continuity_evidence(
            SimpleNamespace(), SYMBOL)["ingress_metrics"], "UNAVAILABLE")


class FenceToEmergencyCloseTests(unittest.TestCase):
    """The unchanged end-to-end feed-gap acceptance, observed through its incidents."""

    def _run_acceptance(self, submit):
        captured = []

        def capture(**kwargs):
            captured.append(kwargs)
            return record_robot_incident(**kwargs)

        with patch.object(paper_runtime, "record_robot_incident", side_effect=capture), \
                patch.object(paper_runtime._DIAGNOSTICS_WRITER, "submit", side_effect=submit):
            result = unittest.TestResult()
            acceptance.RobotPaperDeterministicAcceptanceTests(FEED_GAP).run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        return captured

    def test_emergency_close_links_the_fence_that_started_its_recovery(self):
        captured = self._run_acceptance(lambda write: (write(), True)[1])
        fences = [c for c in captured if c["incident_type"] == "ROBOT_PROTECTION_CONTINUITY_FENCE"]
        closes = [c for c in captured if c["incident_type"] == "ROBOT_PROTECTION_EMERGENCY_CLOSE"]
        self.assertEqual((len(fences), len(closes)), (1, 1))
        fence, close = fences[0]["facts"], closes[0]["facts"]
        self.assertEqual(fence["continuity_reason"], "acceptance_gap")
        self.assertEqual(close["continuity_fence_id"], fence["fence_id"])
        self.assertEqual(close["continuity_fence_reason"], "acceptance_gap")
        self.assertEqual(close["continuity_fence_symbol"], fence["fence_symbol"])
        self.assertEqual(close["continuity_fence_at_ms"], fence["fenced_at_ms"])
        self.assertEqual(close["recovery_reason"], "acceptance_gap")
        self.assertEqual(close["recovery_event_id"], "coverage-recovery-snapshot")
        self.assertIn("recovery_source_generation", close)
        self.assertEqual(closes[0]["reason_code"], "MARKET_DATA_CONTINUITY_LOST")

    def test_failing_diagnostics_leave_the_protection_lifecycle_unchanged(self):
        def broken(_write):
            raise OSError("diagnostics writer unavailable")

        # The acceptance itself asserts fence, recovery, EMERGENCY_CLOSE, Flat and
        # the resolved obligation; it must still pass with the writer failing.
        captured = self._run_acceptance(broken)
        self.assertEqual(
            [c["incident_type"] for c in captured], ["ROBOT_PROTECTION_EMERGENCY_CLOSE"])


if __name__ == "__main__":
    unittest.main()
