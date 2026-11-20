"""Offline contracts for one-shot owner monolith operations."""
import subprocess
import unittest
from types import SimpleNamespace

from tools import vps_owner_control as control

R = "a" * 32
SHA = "b" * 40


def completed(cmd, code=0, out=""):
    return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")


class OwnerControlTests(unittest.TestCase):
    def test_update_postcheck_is_read_only_and_fails_closed(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        target = "b" * 40
        identity = "a" * 64
        data = {
            "/api/health": {"ok": True, "component": "paper_backend",
                            "mode": "paper", "build_sha": target,
                            "paper_live_safe": True, "robot_admission_ready": False,
                            "database_identity": identity},
            "/api/scanner/status": {"ok": True, "mode": "SCANNER_STOPPED",
                                     "worker_quiescent": True},
            "/api/robot/autopilot": {"ok": True, "mode": "OFF"},
            "/api/robot/protection-health": {"ok": True, "healthy": True,
                         "covered_symbols": [], "armed_symbols": [],
                         "coverage_roles": {}, "unhealthy_symbols": {}},
            "/health": {"component": "telegram_monitoring",
                         "status": "ready", "database_identity": identity},
        }

        def getter(url, timeout):
            self.assertEqual(timeout, 3)
            key = "/health" if ":8766" in url else url.split(":8765", 1)[1]
            return SimpleNamespace(status=200, json=lambda: data[key])

        def check():
            out = StringIO()
            with redirect_stdout(out):
                result = control.verify_update(target)
            return result, out.getvalue()

        from unittest.mock import Mock
        from unittest.mock import patch as mock_patch
        import sys
        fake = SimpleNamespace(
            _durable_editor_freeze=Mock(return_value=identity),
            _paper_start_quiescent=Mock(return_value=True),
        )
        with (patch("tools.vps_release_identity.verify_release", return_value=target),
              patch("tools.runtime_intent.http_get", side_effect=getter),
              mock_patch.dict(sys.modules, {"tools.paper_maintenance": fake})):
            self.assertEqual(check()[0], 0)
            self.assertIn("POSTCHECK=VERIFIED_EDITOR_ONLY", check()[1])
            data["/api/robot/protection-health"]["covered_symbols"] = ["BTCUSDT"]
            self.assertEqual(check()[0], 2)
            data["/api/robot/protection-health"]["covered_symbols"] = []
            data["/health"]["database_identity"] = "c" * 64
            self.assertEqual(check()[0], 2)
        self.assertEqual(control.verify_update("invalid"), 2)

    def test_finished_status_requires_bound_update_postcheck(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        output = ("LoadState=loaded\nActiveState=active\nSubState=exited\n"
                  "Result=success\nExecMainStatus=0\n"
                  "Description=BybitScanner update " + SHA[:12] + " origin=win-laptop\n")
        run = lambda cmd, **kw: completed(cmd, out=output)
        for proof, expected in ((0, 0), (2, 2)):
            with patch.object(control, "verify_update", return_value=proof) as check:
                with redirect_stdout(StringIO()) as reply:
                    self.assertEqual(control.status(R, run=run, verify_sha=SHA), expected)
                self.assertIn("STATUS=FINISHED_OK", reply.getvalue())
                check.assert_called_once_with(SHA)
        with patch.object(control, "verify_update") as check:
            self.assertEqual(control.status(R, run=run), 0)
            check.assert_not_called()
        unrelated = output.replace("BybitScanner update", "BybitScanner start")
        with patch.object(control, "verify_update") as check:
            with redirect_stdout(StringIO()) as receipt:
                self.assertEqual(
                    control.status(R, run=lambda cmd, **kw: completed(cmd, out=unrelated),
                                   verify_sha=SHA), 2)
            self.assertIn("POSTCHECK=BLOCKED_REQUEST_TARGET_MISMATCH", receipt.getvalue())
            check.assert_not_called()

    def test_invalid_update_proof_does_not_skip_durable_checks(self):
        import sys
        from unittest.mock import patch, Mock
        fake = SimpleNamespace(
            _durable_editor_freeze=Mock(side_effect=ValueError("PAPER_unproven")),
            _paper_start_quiescent=Mock(return_value=True),
        )
        with (patch("tools.vps_release_identity.verify_release", return_value=SHA),
              patch.dict(sys.modules, {"tools.paper_maintenance": fake}),
              patch("tools.runtime_intent.http_get") as getter):
            self.assertEqual(control.verify_update(SHA), 2)
            fake._durable_editor_freeze.assert_called_once()
            fake._paper_start_quiescent.assert_not_called()
            getter.assert_not_called()

    def test_submit_detaches_exact_action_without_shell_or_runtime_bypass(self):
        calls = []

        def run(cmd, **_kw):
            calls.append(cmd)
            if cmd[0] == "systemctl":
                return completed(cmd, out="LoadState=not-found\n")
            return completed(cmd, out="Running as unit")

        self.assertEqual(control.submit("update", SHA, R, "win-DESKTOP", run=run, uid=0), 0)
        self.assertEqual(len(calls), 2)
        started = calls[1]
        self.assertEqual(started[0], "systemd-run")
        self.assertIn("--no-block", started)
        self.assertIn("--remain-after-exit", started)
        self.assertIn("--property=Type=oneshot", started)
        self.assertIn("--unit=" + control.unit_name(R), started)
        self.assertEqual(started[-5:], ["-m", "tools.paper_maintenance", SHA,
                                         "--action", "update"])
        self.assertNotIn("systemctl stop", " ".join(started))

    def test_pairing_uses_existing_detached_owner_operation_without_secret_in_argv(self):
        calls = []

        def run(cmd, **_kw):
            calls.append(cmd)
            if cmd[0] == "systemctl":
                return completed(cmd, out="LoadState=not-found\n")
            return completed(cmd, out="Running as unit")

        self.assertEqual(control.submit("provision-owner-pc", SHA, R,
                                        "win-DESKTOP", run=run, uid=0), 0)
        started = calls[-1]
        self.assertEqual(started[-5:], ["-m", "tools.paper_maintenance", SHA,
                                         "--action", "provision-owner-pc"])
        self.assertEqual(len(calls), 2)
        self.assertNotIn("BYBITSCANNER_SIMULATOR_BRIDGE", " ".join(started))

    def test_duplicate_request_never_restarts_release(self):
        calls = []

        def run(cmd, **_kw):
            calls.append(cmd)
            if "--property=LoadState" in cmd:
                return completed(cmd, out="LoadState=loaded\n")
            return completed(cmd, out=(
                "LoadState=loaded\nActiveState=active\nSubState=exited\n"
                "Result=success\nExecMainStatus=0\n"))

        self.assertEqual(control.submit("stop", SHA, R, "vps-console",
                                        run=run, uid=0), 0)
        self.assertFalse(any(cmd[0] == "systemd-run" for cmd in calls))

    def test_unknown_submission_is_never_automatically_replayed(self):
        calls = []

        def run(cmd, **_kw):
            calls.append(cmd)
            if cmd[0] == "systemctl":
                return completed(cmd, out="LoadState=not-found\n")
            return completed(cmd, 1)

        self.assertEqual(control.submit("update", SHA, R, "vps-console",
                                        run=run, uid=0), 2)
        self.assertEqual(sum(cmd[0] == "systemd-run" for cmd in calls), 1)

    def test_invalid_inputs_rejected_before_systemd(self):
        def forbidden(*_a, **_kw):
            self.fail("no subprocess on invalid intent")

        for action, sha, req, origin, uid in (
            ("delete", SHA, R, "vps-console", 0),
            ("update", "installed", R, "vps-console", 0),
            ("update", SHA, "invalid", "vps-console", 0),
            ("update", SHA, R, "a;id", 0),
            ("stop", SHA, R, "vps-console", 1000),
        ):
            with self.subTest(action=action, sha=sha, req=req, origin=origin):
                with self.assertRaises(ValueError):
                    control.submit(action, sha, req, origin, run=forbidden, uid=uid)

    def test_status_distinguishes_finished_running_failed_and_unproven(self):
        template = "LoadState=loaded\nActiveState={active}\nSubState={sub}\nResult={result}\nExecMainStatus={code}\n"
        for active, sub, result, code, expected in (
            ("active", "exited", "success", "0", 0),
            ("activating", "start", "success", "0", 3),
            ("failed", "failed", "exit-code", "2", 2),
            ("inactive", "dead", "success", "0", 2),
            ("inactive", "dead", "", "0", 2),
            ("active", "running", "success", "0", 3),
            ("active", "exited", "success", "1", 2),
        ):
            with self.subTest(active=active):
                self.assertEqual(control.status(R, run=lambda cmd, **_kw: completed(
                    cmd, out=template.format(active=active, sub=sub, result=result, code=code))),
                    expected)
        self.assertEqual(control.status(R, run=lambda cmd, **_kw: completed(
            cmd, out="LoadState=not-found\n")), 2)

    def test_inactive_owner_unit_is_never_reported_as_running(self):
        response = ("LoadState=loaded\nActiveState=inactive\nSubState=dead\n"
                    "Result=success\nExecMainStatus=0\n")
        import io
        from contextlib import redirect_stdout
        printed = io.StringIO()
        with redirect_stdout(printed):
            exit_code = control.status(
                R, run=lambda cmd, **_kw: completed(cmd, out=response))
        self.assertEqual(exit_code, 2)
        self.assertIn("STATUS=UNPROVEN", printed.getvalue())
        self.assertNotIn("STATUS=RUNNING", printed.getvalue())

    def test_console_lists_same_requests_without_mutation(self):
        calls = []

        def run(cmd, **_kw):
            calls.append(cmd)
            return completed(cmd, out=control.unit_name(R) + " loaded active exited ...\n")

        self.assertEqual(control.list_requests(run=run), 0)
        self.assertEqual(calls[0][0:2], ["systemctl", "list-units"])


if __name__ == "__main__":
    unittest.main()
