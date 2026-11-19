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
    def test_pinned_reconcile_uses_existing_detached_owner_action(self):
        from unittest.mock import patch
        calls = []
        def run(cmd, **_kw):
            calls.append(cmd)
            return completed(cmd, out="LoadState=not-found\n" if cmd[0] == "systemctl"
                             else "Running as unit")
        with patch("tools.vps_release_identity.verify_release", return_value="b" * 40):
            result = control.submit("reconcile", "installed", R, "win-laptop",
                                    run=run, uid=0)
        self.assertEqual(result, 0)
        self.assertEqual(calls[-1][-5:],
                         ["-m", "tools.paper_maintenance", "b" * 40,
                          "--action", "reconcile"])
        self.assertFalse(any("stop" in " ".join(c).lower()
                             for c in calls if c[0] == "systemd-run"))

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
