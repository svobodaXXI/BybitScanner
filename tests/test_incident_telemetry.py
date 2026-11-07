"""#449 bounded incident evidence; no sockets, production PAPER DB or secrets."""
import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from terminal.runtime import incident_telemetry as telemetry
from robot_failure_diagnostics import MAX_INCIDENT_RECORDS, load_recent_robot_incidents
from terminal.runtime.paper_http_server import SerializedPaperRuntime, ProtectionIngressOverflow


class IncidentTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "owner_incidents"
        self.events = telemetry.IncidentTelemetry(directory=self.directory)
        self.addCleanup(self.events.close)

    def test_redaction_allowlist_and_durable_bounded_atomic_records(self):
        for index in range(MAX_INCIDENT_RECORDS + 9):
            self.assertTrue(self.events.publish(
                "OWNER_SLOW", event_id=f"BTCUSDT:{1000+index}:1",
                task_kind="protection",
                task_label="owner_callback",
                processing_ms=205.6, queue_depth=1,
                symbol="BTCUSDT", role="EXPOSURE",
                credentials="secretTokenHere",
                raw_exception="socks5h://alice:s3cret@localhost?token=secretTokenHere",
            ))
            # Drain in bounded steps to avoid intentionally filling the queue.
            if index % 30 == 29:
                self.events.queue.join()
        self.assertTrue(self.events.close())
        records = load_recent_robot_incidents(incident_dir=self.directory, limit=MAX_INCIDENT_RECORDS + 100)
        self.assertEqual(len(records), MAX_INCIDENT_RECORDS)
        self.assertEqual(records[0]["facts"]["incident_id"], "BTCUSDT:1208:1")
        serialized = "".join(p.read_text() for p in self.directory.glob("*.json"))
        for secret in ("secretTokenHere", "alice", "s3cret", "localhost", "credentials"):
            self.assertNotIn(secret, serialized)
        self.assertIn("OWNER_SLOW", serialized)

    def test_invalid_text_and_unknown_kinds_never_expose_credentials(self):
        self.assertFalse(self.events.publish("ARBITRARY", password="secret"))
        self.assertTrue(self.events.publish(
            "WS_DISCONNECT", event_id="Authorization:Bearer:secret",
            error_class="OSError token=secret", contexts=2,
            generation=4, symbol="BTCUSDT?token=secret", unexpected="secret",
        ))
        self.events.queue.join()
        result = load_recent_robot_incidents(incident_dir=self.directory)[0]
        self.assertEqual(result["facts"]["error_class"], "UNAVAILABLE")
        self.assertEqual(result["facts"]["symbol"], "UNKNOWN")
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(len(result["facts"]["incident_id"]), 32)

    def test_full_queue_never_waits_for_slow_filesystem(self):
        entered, release = threading.Event(), threading.Event()
        def hung_writer(**_):
            entered.set()
            release.wait(timeout=5)
            return True
        another = telemetry.IncidentTelemetry(
            directory=self.directory / "blocked", capacity=3, writer=hung_writer,
        )
        self.addCleanup(release.set)
        self.addCleanup(another.close)
        self.assertTrue(another.publish("INGRESS_WATERMARK", capacity=64, pending=32))
        self.assertTrue(entered.wait(2))
        start = time.perf_counter()
        outcomes = [another.publish("INGRESS_OVERFLOW", capacity=64, pending=64)
                    for _ in range(1500)]
        self.assertLess(time.perf_counter() - start, 1.0)
        self.assertIn(False, outcomes)
        self.assertGreater(another.dropped, 0)
        self.assertLessEqual(another.queue.qsize(), 3)
        release.set()

    def test_owner_diagnostic_attribution_and_ingress_fence_unchanged(self):
        owner = object.__new__(SerializedPaperRuntime)
        owner._owner_diagnostics_disabled = False
        owner._slowest_owner_task = (0.0, "", "")
        owner._requests = queue.Queue()
        owner._thread = type("Alive", (), {"is_alive": lambda self: True})()
        owner._shutdown_gate = threading.Lock()
        owner._shutdown_sealed = False
        owner._protection_ingress_lock = threading.Lock()
        owner._protection_ingress_capacity = 1
        owner._protection_ingress_pending = 0
        owner._protection_ingress_high_watermark = 0
        owner._protection_ingress_last_symbol = None
        owner._protection_ingress_last_role = None
        owner._protection_ingress_last_overflow_symbol = None
        owner._protection_ingress_last_overflow_role = None
        owner._protection_tasks = __import__("collections").deque()
        owner._protection_wake_pending = False
        with patch.object(telemetry, "_active", self.events):
            owner._observe_owner_task(
                "protection", lambda _: None, 305,
                event_id="BTCUSDT:1234:56", ingress_queue_latency_ms=405,
                ingress_pending=1, symbol="BTCUSDT", role="EXPOSURE",
            )
            owner.enqueue(lambda _: None, symbol="BTCUSDT",
                          coverage_role="EXPOSURE", event_id="BTCUSDT:1234:56")
            with self.assertRaises(ProtectionIngressOverflow):
                owner.enqueue(lambda _: None, symbol="BTCUSDT",
                              coverage_role="EXPOSURE", event_id="BTCUSDT:1234:57")
        self.assertEqual(owner._protection_ingress_pending, 1)
        self.events.queue.join()
        observed = {x["stage"] for x in load_recent_robot_incidents(
            incident_dir=self.directory)}
        self.assertEqual(observed, {"OWNER_SLOW", "INGRESS_WATERMARK", "INGRESS_OVERFLOW"})

    def test_not_configured_is_nonfatal_and_does_not_write(self):
        with patch.object(telemetry, "_active", None):
            self.assertFalse(telemetry.report_incident(
                "OWNER_SLOW", task_label="token=SECRET",
            ))


if __name__ == "__main__":
    unittest.main()
