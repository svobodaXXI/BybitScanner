"""Backend wiring for POST /api/runtime/intent (RUNTIME_INTENT_RECONCILER_PLAN.md Slice B).

Policy semantics live in test_runtime_intent_reconciler; these tests prove the
HTTP boundary, port binding to backend primitives, and intent serialization.
"""

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

from terminal.runtime.paper_http_server import PaperHttpHandler


STOPPED = ("ROBOT_STOPPED", "ROBOT_STOPPED")
READY = ("ROBOT_RUNNING", "READY")
PAUSED = ("ROBOT_RUNNING", "PAUSED")
RECON = ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")


class FakePaperRuntime:
    def __init__(self, *, robot=STOPPED, scanner="SCANNER_STOPPED"):
        self.robot = robot
        self.scanner = scanner
        self.calls = []
        self.start_gate = None

    live_gates = {
        "live_market_mutations_enabled": False,
        "live_mainnet_authorized": False,
        "live_market_acceptance_single_flight": False,
        "live_parity_mutations_enabled": False,
        "live_limit_mutations_enabled": False,
        "live_market_acceptance_notional_ceiling": "0",
        "live_limit_acceptance_notional_ceiling": "0",
    }

    database_identity = "a" * 64

    def live_limit_acceptance_diagnostics(self):
        return {"live_gates": dict(self.live_gates), "database_identity": self.database_identity}

    def robot_runtime_state(self):
        return SimpleNamespace(mode=self.robot[0], recovery_status=self.robot[1])

    def robot_start(self):
        self.calls.append("robot:start")
        if self.start_gate is not None:
            self.start_gate()
        assert self.robot == STOPPED
        self.robot = READY

    def robot_resume(self):
        self.calls.append("robot:resume")
        assert self.robot == PAUSED
        self.robot = READY

    def robot_reconcile(self):
        self.calls.append("robot:reconcile")
        assert self.robot == RECON
        self.robot = PAUSED
        return SimpleNamespace(success=True, reason=None)

    def scanner_status(self):
        return SimpleNamespace(mode=self.scanner)

    def start_scanner(self):
        self.calls.append("scanner:start")
        assert self.scanner == "SCANNER_STOPPED"
        self.scanner = "SCANNER_RUNNING"

    def resume_scanner(self):
        self.calls.append("scanner:resume")
        assert self.scanner == "SCANNER_PAUSED"
        self.scanner = "SCANNER_RUNNING"


class FakeSerializedRuntime:
    def __init__(self, runtime):
        self.runtime = runtime

    def call(self, operation, timeout=15.0):
        return operation(self.runtime)


class FakeProtection:
    def __init__(self, healthy=True, unhealthy_symbols=None):
        self.healthy = healthy
        self.unhealthy_symbols = unhealthy_symbols or {}

    def health(self):
        return {"healthy": self.healthy, "unhealthy_symbols": dict(self.unhealthy_symbols)}


class RecordingLock:
    def __init__(self):
        self._lock = threading.Lock()
        self._attempts = 0
        self._guard = threading.Lock()
        self.second_waiting = threading.Event()

    def __enter__(self):
        with self._guard:
            self._attempts += 1
            if self._attempts == 2:
                self.second_waiting.set()
        self._lock.acquire()
        return self

    def __exit__(self, *exc):
        self._lock.release()
        return False


class _BackendServerMixin:
    def setUp(self):
        patcher = mock.patch(
            "terminal.runtime.paper_http_server._scanner_acceptance_ready", return_value=True,
        )
        self.acceptance_ready = patcher.start()
        self.addCleanup(patcher.stop)

    def _serve(self, runtime, protection=None, lock=None, operator_token=None):
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        if operator_token is not None:
            server.operator_token = operator_token
        server.runtime = FakeSerializedRuntime(runtime)
        server.robot_protection_coverage = protection or FakeProtection()
        server.runtime_intent_lock = lock or threading.Lock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        server.serving_thread = thread
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def _post(self, server, body, path="/api/runtime/intent"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        try:
            connection.request(
                "POST", path, body=raw,
                headers={"Content-Type": "application/json", "Content-Length": str(len(raw))},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()


class RuntimeIntentBackendTests(_BackendServerMixin, unittest.TestCase):
    def test_exact_safe_stop_state_converges_through_all(self):
        runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
        status, payload = self._post(self._serve(runtime), {"intent": "ALL"})
        self.assertEqual(status, 200)
        self.assertEqual(payload, {
            "ok": True,
            "intent": "ALL",
            "changed": ["robot:start", "scanner:start"],
            "final": {"robot": "READY", "scanner": "RUNNING", "protection": "HEALTHY"},
            "blocked_by": [],
        })
        self.assertEqual(runtime.calls, ["robot:start", "scanner:start"])

    def test_already_converged_all_is_a_noop(self):
        runtime = FakePaperRuntime(robot=READY, scanner="SCANNER_RUNNING")
        status, payload = self._post(self._serve(runtime), {"intent": "ALL"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["changed"], [])
        self.assertEqual(runtime.calls, [])

    def test_unhealthy_protection_blocks_scanner_with_409(self):
        for protection in (
            FakeProtection(healthy=False),
            FakeProtection(healthy=True, unhealthy_symbols={"BLENDUSDT": "overflow"}),
        ):
            with self.subTest(protection=protection.health()):
                runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
                status, payload = self._post(self._serve(runtime, protection), {"intent": "ALL"})
                self.assertEqual(status, 409)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["blocked_by"], ["ROBOT_PROTECTION_UNHEALTHY"])
                self.assertEqual(runtime.calls, ["robot:start"])
                self.assertEqual(runtime.scanner, "SCANNER_STOPPED")

    def test_invalid_payload_is_400_without_mutation(self):
        bodies = (
            {"intent": "all"},
            {"intent": "BOGUS"},
            {"intent": 1},
            {},
            {"intent": "ALL", "force": True},
            ["ALL"],
            b"not-json",
        )
        runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
        server = self._serve(runtime)
        for body in bodies:
            with self.subTest(body=body):
                status, payload = self._post(server, body)
                self.assertEqual(status, 400)
                self.assertEqual(payload, {"ok": False, "error": "invalid_runtime_intent"})
        self.assertEqual(runtime.calls, [])

    def test_robot_intent_leaves_scanner_untouched(self):
        runtime = FakePaperRuntime(robot=PAUSED, scanner="SCANNER_STOPPED")
        status, payload = self._post(self._serve(runtime), {"intent": "ROBOT"})
        self.assertEqual(status, 200)
        self.assertEqual(runtime.calls, ["robot:resume"])
        self.assertEqual(runtime.scanner, "SCANNER_STOPPED")

    def test_scanner_intent_leaves_robot_untouched(self):
        runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_PAUSED")
        status, payload = self._post(
            self._serve(runtime, FakeProtection(healthy=False)), {"intent": "SCANNER"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(runtime.calls, ["scanner:resume"])
        self.assertEqual(runtime.robot, STOPPED)

    def test_reconcile_uses_backend_primitive_without_http_self_call(self):
        runtime = FakePaperRuntime(robot=RECON, scanner="SCANNER_RUNNING")
        server = self._serve(runtime)
        forbidden = AssertionError("runtime intent must not make an HTTP request")
        with mock.patch("requests.Session.request", side_effect=forbidden) as session_request, \
                mock.patch("requests.post", side_effect=forbidden) as requests_post, \
                mock.patch("urllib.request.urlopen", side_effect=forbidden) as urlopen:
            status, payload = self._post(server, {"intent": "ROBOT"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["changed"], ["robot:reconcile", "robot:resume"])
        self.assertEqual(runtime.calls.count("robot:reconcile"), 1)
        session_request.assert_not_called()
        requests_post.assert_not_called()
        urlopen.assert_not_called()

    def test_effective_live_gates_block_every_intent_with_409(self):
        unsafe = (
            ("live_limit_mutations_enabled", True, None),
            ("live_market_acceptance_notional_ceiling", "5", None),
            (None, None, "x" * 32),
        )
        for gate, value, token in unsafe:
            for intent in ("SCANNER", "ROBOT", "ALL"):
                with self.subTest(gate=gate, token=bool(token), intent=intent):
                    runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
                    if gate is not None:
                        runtime.live_gates = {**FakePaperRuntime.live_gates, gate: value}
                    server = self._serve(runtime, operator_token=token)
                    status, payload = self._post(server, {"intent": intent})
                    self.assertEqual(status, 409)
                    self.assertEqual(payload["blocked_by"], ["PAPER_LIVE_UNSAFE"])
                    self.assertEqual(runtime.calls, [])

    def test_scanner_acceptance_config_gates_scanner_and_all_but_not_robot(self):
        self.acceptance_ready.return_value = False
        for intent, expected in (("SCANNER", 409), ("ALL", 409), ("ROBOT", 200)):
            with self.subTest(intent=intent):
                runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
                status, payload = self._post(self._serve(runtime), {"intent": intent})
                self.assertEqual(status, expected)
                if expected == 409:
                    self.assertEqual(payload["blocked_by"], ["SCANNER_ACCEPTANCE_NOT_READY"])
                    self.assertEqual(runtime.calls, [])
                else:
                    self.assertEqual(runtime.calls, ["robot:start"])

    def test_concurrent_intents_never_overlap_mutation_sections(self):
        runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
        lock = RecordingLock()
        entered = threading.Event()
        release = threading.Event()

        def gate():
            entered.set()
            self.assertTrue(release.wait(10))

        runtime.start_gate = gate
        server = self._serve(runtime, lock=lock)
        results = {}

        def send(name):
            results[name] = self._post(server, {"intent": "ROBOT"})

        first = threading.Thread(target=send, args=("first",))
        first.start()
        self.assertTrue(entered.wait(10))
        second = threading.Thread(target=send, args=("second",))
        second.start()
        self.assertTrue(lock.second_waiting.wait(10))
        self.assertEqual(runtime.calls, ["robot:start"])
        release.set()
        first.join(10)
        second.join(10)

        self.assertEqual(runtime.calls, ["robot:start"])
        self.assertEqual(results["first"][0], 200)
        self.assertEqual(results["first"][1]["changed"], ["robot:start"])
        self.assertEqual(results["second"][0], 200)
        self.assertEqual(results["second"][1]["changed"], [])


class RuntimeShutdownBackendTests(_BackendServerMixin, unittest.TestCase):
    SHUTDOWN = "/api/runtime/shutdown"

    def test_shutdown_rejects_wrong_or_missing_identity_and_keeps_serving(self):
        runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
        server = self._serve(runtime)
        for body, status in (
            ({"database_identity": "0" * 64}, 409),
            ({"database_identity": ("a" * 64).upper()}, 409),
            ({}, 400),
            ({"database_identity": ""}, 400),
            ({"database_identity": 1}, 400),
            ({"database_identity": "a" * 64, "force": True}, 400),
            (b"not json", 400),
        ):
            with self.subTest(body=body):
                self.assertEqual(self._post(server, body, self.SHUTDOWN)[0], status)
                self.assertTrue(server.serving_thread.is_alive())

    def test_shutdown_refuses_while_robot_scanner_or_protection_still_need_backend(self):
        for robot, scanner, protection in (
            (READY, "SCANNER_STOPPED", FakeProtection()),
            (PAUSED, "SCANNER_STOPPED", FakeProtection()),
            (RECON, "SCANNER_STOPPED", FakeProtection()),
            (STOPPED, "SCANNER_RUNNING", FakeProtection()),
            (STOPPED, "SCANNER_STOPPED", FakeProtection(healthy=False)),
            (STOPPED, "SCANNER_STOPPED", FakeProtection(unhealthy_symbols={"BTCUSDT": "x"})),
        ):
            with self.subTest(robot=robot, scanner=scanner):
                runtime = FakePaperRuntime(robot=robot, scanner=scanner)
                server = self._serve(runtime, protection)
                status, payload = self._post(server, {"database_identity": "a" * 64}, self.SHUTDOWN)
                self.assertEqual((status, payload["error"]), (409, "runtime_still_required"))
                self.assertTrue(server.serving_thread.is_alive())

    def test_exact_identity_on_quiescent_runtime_stops_serving_after_reply(self):
        runtime = FakePaperRuntime(robot=STOPPED, scanner="SCANNER_STOPPED")
        server = self._serve(runtime)
        status, payload = self._post(server, {"database_identity": "a" * 64}, self.SHUTDOWN)
        self.assertEqual((status, payload), (200, {"ok": True, "shutdown": "scheduled"}))
        server.serving_thread.join(5)
        self.assertFalse(server.serving_thread.is_alive())
        self.assertEqual(runtime.calls, [])


if __name__ == "__main__":
    unittest.main()
