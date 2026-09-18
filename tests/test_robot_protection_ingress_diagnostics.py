from __future__ import annotations

import threading
import unittest

from terminal.runtime.paper_http_server import (
    ProtectionIngressOverflow,
    RobotProtectionCoverageManager,
    SerializedPaperRuntime,
)


class _SerializedOwner:
    def close(self) -> None:
        return None


class _CoverageOwner:
    def robot_protection_coverage_targets(self):
        return {"EDGEUSDT": "ENTRY_PENDING"}

    def robot_protection_continuity_loss(self):
        return None


class _DirectRuntime:
    def __init__(self) -> None:
        self.owner = _CoverageOwner()

    def call(self, operation, timeout=15.0):
        return operation(self.owner)


class _Context:
    def __init__(self) -> None:
        self.listeners = {}

    def add_update_listener(self, name, listener):
        self.listeners[name] = listener

    def remove_update_listener(self, name):
        self.listeners.pop(name, None)


class _Hub:
    def __init__(self) -> None:
        self.context = _Context()

    def subscribe(self, symbol):
        return self.context

    def discard(self, context):
        return None


class RobotProtectionIngressDiagnosticsTests(unittest.TestCase):
    def test_bounded_ingress_reports_high_watermark_latency_and_overflow_identity(self):
        runtime = SerializedPaperRuntime(
            _SerializedOwner,
            protection_ingress_capacity=1,
        )
        entered = threading.Event()
        release = threading.Event()

        def exposure_task(owner):
            entered.set()
            release.wait(2)

        setattr(exposure_task, "_robot_ingress_symbol", "KSMUSDT")
        setattr(exposure_task, "_robot_ingress_role", "EXPOSURE")

        def entry_task(owner):
            return None

        setattr(entry_task, "_robot_ingress_symbol", "EDGEUSDT")
        setattr(entry_task, "_robot_ingress_role", "ENTRY_PENDING")

        try:
            runtime.enqueue(exposure_task)
            self.assertTrue(entered.wait(1))

            before = runtime.protection_ingress_diagnostics()
            self.assertEqual(before["capacity"], 1)
            self.assertEqual(before["pending"], 1)
            self.assertEqual(before["high_watermark"], 1)
            self.assertEqual(before["admitted"], 1)
            self.assertEqual(before["completed"], 0)

            with self.assertRaises(ProtectionIngressOverflow):
                runtime.enqueue(entry_task)

            overflow = runtime.protection_ingress_diagnostics()
            self.assertEqual(overflow["overflows"], 1)
            self.assertEqual(overflow["last_overflow_symbol"], "EDGEUSDT")
            self.assertEqual(overflow["last_overflow_role"], "ENTRY_PENDING")
            self.assertEqual(overflow["last_overflow_pending"], 1)

            release.set()
            runtime.call(lambda owner: None)

            after = runtime.protection_ingress_diagnostics()
            self.assertEqual(after["pending"], 0)
            self.assertEqual(after["completed"], 1)
            self.assertEqual(after["last_symbol"], "KSMUSDT")
            self.assertEqual(after["last_role"], "EXPOSURE")
            self.assertGreaterEqual(after["max_queue_latency_ms"], 0)
            self.assertGreaterEqual(after["max_processing_ms"], 0)
        finally:
            release.set()
            runtime.close()

    def test_coverage_manager_exposes_lifecycle_role_from_owner(self):
        manager = RobotProtectionCoverageManager(
            _Hub(),
            _DirectRuntime(),
        )
        try:
            manager.resync()
            health = manager.health()
            self.assertEqual(health["covered_symbols"], ("EDGEUSDT",))
            self.assertEqual(
                health["coverage_roles"],
                {"EDGEUSDT": "ENTRY_PENDING"},
            )
        finally:
            manager.close()


if __name__ == "__main__":
    unittest.main()
