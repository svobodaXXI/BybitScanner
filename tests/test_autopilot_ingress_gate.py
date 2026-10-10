"""#448 / S2: Autopilot admission is fail-closed under ingress overload or unknown metrics.

The Autopilot protection-health source used to be only `coverage.is_healthy()`:
True until an overflow had already latched. The observer runs on the owner
thread AFTER every admitted protection task is drained, so an instantaneous
`current_pending` is ~0 at the decision instant, and the latency/processing
metrics are process-lifetime maxima. A burst with 80 s queue latency could
therefore still end in ALLOW. The gate must use a RECENT window and treat
missing metrics as unknown (WAIT), never as healthy. Temporary DBs only.
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from terminal.application.robot_admission import admit_robot_candidate
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_WAIT, REASON_ELIGIBLE, REASON_PROTECTION_HEALTH_UNKNOWN,
    REASON_PROTECTION_UNHEALTHY,
)
from terminal.runtime.paper_http_server import (
    SerializedPaperRuntime, make_autopilot_protection_health,
)
from tests.test_robot_autopilot_shadow import ACCOUNT, _Db, _wedge


class _Coverage:
    def __init__(self, healthy=True):
        self.healthy = healthy

    def is_healthy(self):
        return self.healthy


class _Metrics:
    """Stand-in exposing only the recent-window ingress read the gate may use."""

    def __init__(self, **values):
        self.values = {
            "capacity": 64, "current_pending": 0, "recent_samples": 5,
            "recent_max_queue_latency_ms": 10.0, "recent_max_processing_ms": 5.0,
        }
        self.values.update(values)

    def protection_ingress_recent(self, window_s):
        return dict(self.values)


class IngressGateProviderTests(unittest.TestCase):
    def provider(self, runtime, coverage=None):
        return make_autopilot_protection_health(coverage or _Coverage(), runtime)

    def test_quiet_healthy_ingress_is_healthy(self):
        self.assertIs(self.provider(_Metrics())(), True)

    def test_recent_queue_latency_over_limit_is_unhealthy(self):
        self.assertIs(self.provider(_Metrics(recent_max_queue_latency_ms=84_700.0))(), False)

    def test_recent_slow_owner_task_is_unhealthy(self):
        self.assertIs(self.provider(_Metrics(recent_max_processing_ms=7_900.0))(), False)

    def test_backlog_at_half_capacity_is_unhealthy(self):
        self.assertIs(self.provider(_Metrics(current_pending=32))(), False)
        self.assertIs(self.provider(_Metrics(current_pending=31))(), True)

    def test_coverage_already_unhealthy_stays_unhealthy(self):
        self.assertIs(self.provider(_Metrics(), _Coverage(False))(), False)

    def test_missing_or_invalid_metrics_are_unknown_never_healthy(self):
        for broken in (
            _Metrics(recent_max_queue_latency_ms=None),
            _Metrics(recent_samples="n/a"),
            _Metrics(capacity=0),
            _Metrics(current_pending=-1),
            _Metrics(recent_max_processing_ms=float("nan")),
        ):
            self.assertIsNone(self.provider(broken)())
        self.assertIsNone(self.provider(object())())  # no recent-window source at all

        class Raising:
            def protection_ingress_recent(self, window_s):
                raise RuntimeError("metrics unavailable")

        self.assertIsNone(self.provider(Raising())())


class RecentWindowOnRealIngressTests(unittest.TestCase):
    def test_recent_latency_gates_then_window_expires_and_protection_still_runs(self):
        runtime = SerializedPaperRuntime(lambda: object())
        self.addCleanup(runtime.close)
        release = threading.Event()
        runtime.enqueue(lambda _owned: release.wait(5), symbol="AAAUSDT", coverage_role="EXPOSURE")
        runtime.enqueue(lambda _owned: None, symbol="BBBUSDT", coverage_role="EXPOSURE")
        time.sleep(0.4)  # the second event queues behind the slow one
        release.set()
        deadline = time.time() + 5
        while runtime.protection_ingress_metrics()["current_pending"] and time.time() < deadline:
            time.sleep(0.01)

        gate = make_autopilot_protection_health(
            _Coverage(), runtime, window_s=0.5, max_queue_latency_ms=200.0,
        )
        # After the drain the instantaneous backlog is 0, yet the burst is still visible.
        self.assertEqual(runtime.protection_ingress_metrics()["current_pending"], 0)
        self.assertIs(gate(), False)

        # Existing protection keeps flowing while the gate is closed.
        ran = threading.Event()
        runtime.enqueue(lambda _owned: ran.set(), symbol="CCCUSDT", coverage_role="EXPOSURE")
        self.assertTrue(ran.wait(5))

        time.sleep(0.6)
        self.assertIs(gate(), True)  # quiet window again


class ShadowAdmissionUnderOverloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = _Db(Path(self.tmp.name))
        self.addCleanup(self.db.store.close)

    def test_overload_waits_unknown_waits_and_manual_admission_is_unaffected(self):
        _wedge(self.db.candidates, "w-load", symbol="AAAUSDT")
        _wedge(self.db.candidates, "w-unknown", symbol="BBBUSDT")
        _wedge(self.db.candidates, "w-ok", symbol="CCCUSDT")

        overloaded = make_autopilot_protection_health(
            _Coverage(), _Metrics(recent_max_queue_latency_ms=84_700.0))
        waiting = self.db.observe("w-load", health=overloaded).result
        self.assertEqual((waiting.outcome, waiting.reason_code),
                         (OUTCOME_WAIT, REASON_PROTECTION_UNHEALTHY))

        unknown = make_autopilot_protection_health(_Coverage(), object())
        result = self.db.observe("w-unknown", health=unknown).result
        self.assertEqual((result.outcome, result.reason_code),
                         (OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN))

        allowed = self.db.observe("w-ok", health=make_autopilot_protection_health(
            _Coverage(), _Metrics())).result
        self.assertEqual((allowed.outcome, allowed.reason_code), (OUTCOME_ALLOW, REASON_ELIGIBLE))

        # The gate only feeds the Autopilot policy: the owner's manual lifecycle is untouched.
        record, created = admit_robot_candidate(
            "w-load", database_path=Path(self.tmp.name) / "paper.sqlite3",
            store_dir=self.db.candidates, clock_ms=lambda: 6000,
        )
        self.assertTrue(created)
        self.assertEqual((record.status, record.symbol.value), ("APPROVED", "AAAUSDT"))


if __name__ == "__main__":
    unittest.main()
