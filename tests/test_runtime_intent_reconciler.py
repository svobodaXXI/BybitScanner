"""Slice A contract for the one-action Runtime Intent Reconciler.

Freezes DOCUMENTS/RUNTIME_INTENT_RECONCILER_PLAN.md sections 3, 5.2 and 6
against injected ports that mimic the legality of the existing canonical
primitives (robot_control.start_robot/resume_robot/reconcile_robot and
ScannerControlRuntime.start_scanner/resume_scanner).
"""

import unittest

from terminal.application.runtime_intent import RuntimeIntent, RuntimeIntentReconciler


ROBOT_STOPPED = ("ROBOT_STOPPED", "ROBOT_STOPPED")
ROBOT_READY = ("ROBOT_RUNNING", "READY")
ROBOT_PAUSED = ("ROBOT_RUNNING", "PAUSED")
ROBOT_RECON = ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")
ROBOT_STOPPED_RECON = ("ROBOT_STOPPED", "RECONCILIATION_REQUIRED")
ROBOT_RECONCILING = ("ROBOT_RUNNING", "RECONCILING")

SCANNER_STOPPED = "SCANNER_STOPPED"
SCANNER_RUNNING = "SCANNER_RUNNING"
SCANNER_PAUSED = "SCANNER_PAUSED"


class _Rejected(Exception):
    pass


class FakeRuntimePorts:
    """Canonical-primitive stand-ins that reject illegal transitions."""

    def __init__(
        self,
        *,
        robot=ROBOT_STOPPED,
        scanner=SCANNER_STOPPED,
        protection=True,
        start_lands=ROBOT_READY,
        reconcile_lands=ROBOT_PAUSED,
        reconcile_raises=False,
        paper_safe=True,
        acceptance_ready=True,
    ):
        self.paper_safe = paper_safe
        self.acceptance_ready = acceptance_ready
        self.robot = robot
        self.scanner = scanner
        self.protection = protection
        self.start_lands = start_lands
        self.reconcile_lands = reconcile_lands
        self.reconcile_raises = reconcile_raises
        self.calls = []

    def paper_live_safe(self):
        if isinstance(self.paper_safe, Exception):
            raise self.paper_safe
        return self.paper_safe

    def scanner_acceptance_ready(self):
        if isinstance(self.acceptance_ready, Exception):
            raise self.acceptance_ready
        return self.acceptance_ready

    def robot_state(self):
        return self.robot

    def scanner_state(self):
        return self.scanner

    def protection_healthy(self):
        return self.protection

    def start_robot(self):
        self.calls.append("robot:start")
        if self.robot != ROBOT_STOPPED:
            raise _Rejected("start_robot is legal only from (ROBOT_STOPPED, ROBOT_STOPPED)")
        self.robot = self.start_lands

    def resume_robot(self):
        self.calls.append("robot:resume")
        if self.robot != ROBOT_PAUSED:
            raise _Rejected("resume_robot is legal only from (ROBOT_RUNNING, PAUSED)")
        self.robot = ROBOT_READY

    def reconcile_robot(self):
        self.calls.append("robot:reconcile")
        if self.robot != ROBOT_RECON:
            raise _Rejected("reconcile_robot is legal only from (ROBOT_RUNNING, RECONCILIATION_REQUIRED)")
        if self.reconcile_raises:
            raise _Rejected("reconcile_robot did not complete safely")
        self.robot = self.reconcile_lands

    def start_scanner(self):
        self.calls.append("scanner:start")
        if self.scanner != SCANNER_STOPPED:
            raise _Rejected("start_scanner is legal only from SCANNER_STOPPED")
        self.scanner = SCANNER_RUNNING

    def resume_scanner(self):
        self.calls.append("scanner:resume")
        if self.scanner != SCANNER_PAUSED:
            raise _Rejected("resume_scanner is legal only from SCANNER_PAUSED")
        self.scanner = SCANNER_RUNNING


def _reconcile(ports, intent):
    return RuntimeIntentReconciler(ports).reconcile(intent)


def _robot_calls(ports):
    return [call for call in ports.calls if call.startswith("robot:")]


def _scanner_calls(ports):
    return [call for call in ports.calls if call.startswith("scanner:")]


class RobotIntentContractTests(unittest.TestCase):
    def test_stopped_robot_is_started_to_ready(self):
        ports = FakeRuntimePorts(robot=ROBOT_STOPPED)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ("robot:start",))
        self.assertEqual(result.final["robot"], "READY")
        self.assertEqual(result.final["protection"], "HEALTHY")
        self.assertEqual(tuple(result.blocked_by), ())

    def test_paused_robot_is_resumed_to_ready(self):
        ports = FakeRuntimePorts(robot=ROBOT_PAUSED)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ("robot:resume",))
        self.assertEqual(ports.robot, ROBOT_READY)

    def test_ready_robot_is_a_noop(self):
        ports = FakeRuntimePorts(robot=ROBOT_READY)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ())
        self.assertEqual(ports.calls, [])

    def test_recoverable_reconciliation_required_reconciles_once_then_resumes(self):
        ports = FakeRuntimePorts(robot=ROBOT_RECON, reconcile_lands=ROBOT_PAUSED)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ("robot:reconcile", "robot:resume"))
        self.assertEqual(ports.robot, ROBOT_READY)

    def test_start_landing_in_reconciliation_required_is_re_observed(self):
        ports = FakeRuntimePorts(
            robot=ROBOT_STOPPED, start_lands=ROBOT_RECON, reconcile_lands=ROBOT_PAUSED,
        )
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertTrue(result.ok)
        self.assertEqual(
            tuple(result.changed), ("robot:start", "robot:reconcile", "robot:resume"),
        )

    def test_reconciliation_that_stays_unsafe_is_one_bounded_blocker(self):
        ports = FakeRuntimePorts(robot=ROBOT_RECON, reconcile_lands=ROBOT_RECON)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertFalse(result.ok)
        self.assertEqual(ports.calls.count("robot:reconcile"), 1)
        self.assertIn("ROBOT_RECONCILIATION_REQUIRED", result.blocked_by)

    def test_failed_reconciliation_fails_closed_without_further_mutation(self):
        ports = FakeRuntimePorts(robot=ROBOT_RECON, reconcile_raises=True)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertFalse(result.ok)
        self.assertEqual(ports.calls, ["robot:reconcile"])
        self.assertIn("ROBOT_RECONCILIATION_FAILED", result.blocked_by)

    def test_stopped_with_reconciliation_required_has_no_shortcut(self):
        ports = FakeRuntimePorts(robot=ROBOT_STOPPED_RECON)
        result = _reconcile(ports, RuntimeIntent.ROBOT)
        self.assertFalse(result.ok)
        self.assertEqual(ports.calls, [])
        self.assertIn("ROBOT_STOPPED_RECONCILIATION_REQUIRED", result.blocked_by)

    def test_unknown_or_malformed_robot_state_fails_closed(self):
        for state in (None, ("ROBOT_WEIRD", "READY"), ("ROBOT_RUNNING", "WEIRD"), ROBOT_RECONCILING):
            with self.subTest(state=state):
                ports = FakeRuntimePorts(robot=state)
                result = _reconcile(ports, RuntimeIntent.ROBOT)
                self.assertFalse(result.ok)
                self.assertEqual(ports.calls, [])
                self.assertIn("ROBOT_STATE_UNKNOWN", result.blocked_by)

    def test_unproven_protection_blocks_robot_intent(self):
        for protection in (False, None):
            with self.subTest(protection=protection):
                ports = FakeRuntimePorts(robot=ROBOT_READY, protection=protection)
                result = _reconcile(ports, RuntimeIntent.ROBOT)
                self.assertFalse(result.ok)
                self.assertIn("ROBOT_PROTECTION_UNHEALTHY", result.blocked_by)

    def test_robot_intent_never_mutates_scanner(self):
        for scanner in (SCANNER_STOPPED, SCANNER_PAUSED, SCANNER_RUNNING):
            with self.subTest(scanner=scanner):
                ports = FakeRuntimePorts(robot=ROBOT_STOPPED, scanner=scanner)
                result = _reconcile(ports, RuntimeIntent.ROBOT)
                self.assertTrue(result.ok)
                self.assertEqual(_scanner_calls(ports), [])
                self.assertEqual(ports.scanner, scanner)


class ScannerIntentContractTests(unittest.TestCase):
    def test_stopped_scanner_is_started(self):
        ports = FakeRuntimePorts(robot=ROBOT_READY, scanner=SCANNER_STOPPED)
        result = _reconcile(ports, RuntimeIntent.SCANNER)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ("scanner:start",))
        self.assertEqual(result.final["scanner"], "RUNNING")

    def test_paused_scanner_is_resumed(self):
        ports = FakeRuntimePorts(robot=ROBOT_READY, scanner=SCANNER_PAUSED)
        result = _reconcile(ports, RuntimeIntent.SCANNER)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ("scanner:resume",))

    def test_running_scanner_is_a_noop(self):
        ports = FakeRuntimePorts(robot=ROBOT_READY, scanner=SCANNER_RUNNING)
        result = _reconcile(ports, RuntimeIntent.SCANNER)
        self.assertTrue(result.ok)
        self.assertEqual(tuple(result.changed), ())
        self.assertEqual(ports.calls, [])

    def test_scanner_intent_never_mutates_robot(self):
        for robot in (ROBOT_STOPPED, ROBOT_PAUSED, ROBOT_RECON):
            with self.subTest(robot=robot):
                ports = FakeRuntimePorts(robot=robot, scanner=SCANNER_STOPPED, protection=False)
                result = _reconcile(ports, RuntimeIntent.SCANNER)
                self.assertTrue(result.ok)
                self.assertEqual(_robot_calls(ports), [])
                self.assertEqual(ports.robot, robot)

    def test_unknown_scanner_state_fails_closed(self):
        for state in (None, "SCANNER_WEIRD"):
            with self.subTest(state=state):
                ports = FakeRuntimePorts(robot=ROBOT_READY, scanner=state)
                result = _reconcile(ports, RuntimeIntent.SCANNER)
                self.assertFalse(result.ok)
                self.assertEqual(ports.calls, [])
                self.assertIn("SCANNER_STATE_UNKNOWN", result.blocked_by)


class AllIntentContractTests(unittest.TestCase):
    def test_exact_2026_09_27_safe_stop_state_converges_in_one_action(self):
        ports = FakeRuntimePorts(robot=ROBOT_STOPPED, scanner=SCANNER_STOPPED)
        result = _reconcile(ports, RuntimeIntent.ALL)
        self.assertTrue(result.ok)
        self.assertEqual(result.intent, RuntimeIntent.ALL)
        self.assertEqual(tuple(result.changed), ("robot:start", "scanner:start"))
        self.assertEqual(
            dict(result.final),
            {"robot": "READY", "scanner": "RUNNING", "protection": "HEALTHY"},
        )
        self.assertEqual(tuple(result.blocked_by), ())

    def test_all_prepares_robot_before_touching_scanner(self):
        ports = FakeRuntimePorts(robot=ROBOT_PAUSED, scanner=SCANNER_PAUSED)
        result = _reconcile(ports, RuntimeIntent.ALL)
        self.assertTrue(result.ok)
        self.assertEqual(ports.calls, ["robot:resume", "scanner:resume"])

    def test_all_never_starts_scanner_when_robot_is_blocked(self):
        ports = FakeRuntimePorts(robot=ROBOT_RECON, scanner=SCANNER_STOPPED, reconcile_raises=True)
        result = _reconcile(ports, RuntimeIntent.ALL)
        self.assertFalse(result.ok)
        self.assertEqual(_scanner_calls(ports), [])
        self.assertEqual(ports.scanner, SCANNER_STOPPED)

    def test_all_never_starts_scanner_when_protection_is_unhealthy(self):
        ports = FakeRuntimePorts(robot=ROBOT_STOPPED, scanner=SCANNER_STOPPED, protection=False)
        result = _reconcile(ports, RuntimeIntent.ALL)
        self.assertFalse(result.ok)
        self.assertIn("ROBOT_PROTECTION_UNHEALTHY", result.blocked_by)
        self.assertEqual(_scanner_calls(ports), [])

    def test_all_with_unknown_scanner_blocks_before_any_robot_mutation(self):
        ports = FakeRuntimePorts(robot=ROBOT_STOPPED, scanner=None)
        result = _reconcile(ports, RuntimeIntent.ALL)
        self.assertFalse(result.ok)
        self.assertEqual(ports.calls, [])
        self.assertEqual(ports.robot, ROBOT_STOPPED)
        self.assertIn("SCANNER_STATE_UNKNOWN", result.blocked_by)

    def test_repeated_all_intent_is_idempotent(self):
        ports = FakeRuntimePorts(robot=ROBOT_STOPPED, scanner=SCANNER_STOPPED)
        reconciler = RuntimeIntentReconciler(ports)
        first = reconciler.reconcile(RuntimeIntent.ALL)
        second = reconciler.reconcile(RuntimeIntent.ALL)
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(tuple(second.changed), ())
        self.assertEqual(ports.calls, ["robot:start", "scanner:start"])


class SafetyPreflightContractTests(unittest.TestCase):
    NOT_PROVEN = (False, None, "true", 1, _Rejected("unavailable"))

    def test_paper_live_unsafe_blocks_every_intent_before_any_mutation(self):
        for intent in (RuntimeIntent.SCANNER, RuntimeIntent.ROBOT, RuntimeIntent.ALL):
            for value in self.NOT_PROVEN:
                with self.subTest(intent=intent, value=value):
                    ports = FakeRuntimePorts(
                        robot=ROBOT_STOPPED, scanner=SCANNER_STOPPED, paper_safe=value,
                    )
                    result = _reconcile(ports, intent)
                    self.assertFalse(result.ok)
                    self.assertEqual(tuple(result.blocked_by), ("PAPER_LIVE_UNSAFE",))
                    self.assertEqual(ports.calls, [])

    def test_scanner_acceptance_not_ready_blocks_scanner_and_all_before_any_mutation(self):
        for intent in (RuntimeIntent.SCANNER, RuntimeIntent.ALL):
            for value in self.NOT_PROVEN:
                with self.subTest(intent=intent, value=value):
                    ports = FakeRuntimePorts(
                        robot=ROBOT_STOPPED, scanner=SCANNER_STOPPED, acceptance_ready=value,
                    )
                    result = _reconcile(ports, intent)
                    self.assertFalse(result.ok)
                    self.assertEqual(tuple(result.blocked_by), ("SCANNER_ACCEPTANCE_NOT_READY",))
                    self.assertEqual(ports.calls, [])
                    self.assertEqual(ports.robot, ROBOT_STOPPED)

    def test_robot_intent_ignores_scanner_acceptance(self):
        for value in self.NOT_PROVEN:
            with self.subTest(value=value):
                ports = FakeRuntimePorts(robot=ROBOT_STOPPED, scanner=None, acceptance_ready=value)
                result = _reconcile(ports, RuntimeIntent.ROBOT)
                self.assertTrue(result.ok)
                self.assertEqual(tuple(result.changed), ("robot:start",))


if __name__ == "__main__":
    unittest.main()
