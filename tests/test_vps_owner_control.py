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
        # New units use the full SHA while old ones remain read-only queryable.
        full = output.replace(SHA[:12] + " origin=", SHA + " origin=")
        with patch.object(control, "verify_update", return_value=0) as check:
            self.assertEqual(control.status(
                R, run=lambda cmd, **kw: completed(cmd, out=full),
                verify_sha=SHA,
            ), 0)
            check.assert_called_once_with(SHA)
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
        self.assertIn("--description=BybitScanner update " + SHA + " origin=win-DESKTOP", started)
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
        description = f"BybitScanner stop {SHA} origin=vps-console"

        def run(cmd, **_kw):
            calls.append(cmd)
            if "--property=LoadState,Description" in cmd:
                return completed(cmd, out=f"LoadState=loaded\nDescription={description}\n")
            return completed(cmd, out=(
                "LoadState=loaded\nActiveState=active\nSubState=exited\n"
                f"Result=success\nExecMainStatus=0\nDescription={description}\n"))

        self.assertEqual(control.submit("stop", SHA, R, "vps-console",
                                        run=run, uid=0), 0)
        self.assertFalse(any(cmd[0] == "systemd-run" for cmd in calls))

    def test_same_uuid_different_action_sha_origin_or_legacy_unit_fails_closed(self):
        calls = []
        stored = f"BybitScanner update {SHA} origin=win-pc"

        def run(cmd, **_kw):
            calls.append(cmd)
            return completed(cmd, out="LoadState=loaded\nDescription=" + stored + "\n")

        for action, sha, origin in (
            ("start", SHA, "win-pc"),
            ("update", "c" * 40, "win-pc"),
            ("update", SHA, "win-laptop"),
        ):
            with self.subTest(action=action, sha=sha, origin=origin):
                self.assertEqual(
                    control.submit(action, sha, R, origin, run=run, uid=0), 2,
                )

        # The old short SHA is not a whole-payload identity. It can still be
        # examined through read-only status(), but cannot authorize a submit.
        stored = f"BybitScanner update {SHA[:12]} origin=win-pc"
        self.assertEqual(control.submit(
            "update", SHA, R, "win-pc", run=run, uid=0,
        ), 2)
        self.assertFalse(any(cmd[0] == "systemd-run" for cmd in calls))

    def test_existing_take_closed_uuid_can_be_queried_after_stage_was_removed(self):
        from unittest.mock import patch
        label = f"BybitScanner update-take-closed {SHA} origin=win-pc"
        calls = []

        def run(cmd, **_kw):
            calls.append(cmd)
            if "--property=LoadState,Description" in cmd:
                return completed(cmd, out=f"LoadState=loaded\nDescription={label}\n")
            return completed(cmd, out=(
                "LoadState=loaded\nActiveState=activating\nSubState=start\n"
                f"Result=success\nExecMainStatus=0\nDescription={label}\n"
            ))

        # Reading an existing detached request is independent of its staging
        # checkout; the status remains RUNNING and nothing can be re-submitted.
        with patch.object(control, "_verified_take_closed_stage") as stage:
            self.assertEqual(control.submit(
                "update-take-closed", SHA, R, "win-pc", run=run, uid=0,
            ), 3)
            stage.assert_not_called()
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

    def test_transport_failure_is_unproven_and_never_replayed(self):
        from contextlib import redirect_stdout
        from io import StringIO

        for failure in (OSError("transport"), subprocess.TimeoutExpired("systemd", 20)):
            for phase in ("probe", "dispatch", "status"):
                with self.subTest(failure=type(failure).__name__, phase=phase):
                    calls = []

                    def run(cmd, **_kw):
                        calls.append(cmd[0])
                        if phase != "dispatch" or cmd[0] == "systemd-run":
                            raise failure
                        return completed(cmd, out="LoadState=not-found\n")

                    with redirect_stdout(StringIO()) as reply:
                        if phase == "status":
                            rc = control.status(R, run=run, verify_start_sha=SHA)
                        else:
                            rc = control.submit("update-and-start", SHA, R, "vps-console",
                                                run=run, uid=0)
                    self.assertEqual(rc, 2)
                    self.assertIn(R, reply.getvalue())
                    self.assertIn("STATUS=UNPROVEN" if phase == "status" else
                                  "SUBMISSION=UNPROVEN", reply.getvalue())
                    self.assertNotIn("FINISHED_OK", reply.getvalue())
                    self.assertNotIn("SUBMISSION=ACCEPTED", reply.getvalue())
                    self.assertEqual(calls, ["systemctl", "systemd-run"] if
                                     phase == "dispatch" else ["systemctl"])

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




class StartReceiptOwnerTests(unittest.TestCase):
    def test_start_receipt_requires_exact_bound_current_paper_proof(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        for action, target, expected, rc in (
            ("start", SHA, "installed", 0),
            ("start", SHA, SHA, 0),
            ("update-and-start", SHA, SHA, 0),
            ("stop", SHA, SHA, 2),
            ("start", SHA[:12], "installed", 2),
            ("start", SHA, "c" * 40, 2),
        ):
            output = ("LoadState=loaded\nActiveState=active\nSubState=exited\n"
                      "Result=success\nExecMainStatus=0\n"
                      f"Description=BybitScanner {action} {target} origin=win-laptop\n")
            with patch.object(control, "verify_start", return_value=0) as verify:
                with redirect_stdout(StringIO()):
                    assert control.status(R, run=lambda cmd, **kw: completed(cmd, out=output),
                                          verify_start_sha=expected) == rc
                if rc == 0:
                    verify.assert_called_once_with(SHA)
                else:
                    verify.assert_not_called()


    def test_start_postcheck_uses_readonly_canonical_readiness(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch, Mock
        import sys

        readiness = Mock(return_value="READY: canonical full PAPER")
        fake = SimpleNamespace(_paper_full_readiness=readiness)
        with (patch("tools.vps_release_identity.verify_release", return_value=SHA) as identity,
              patch.dict(sys.modules, {"tools.paper_maintenance": fake})):
            with redirect_stdout(StringIO()) as receipt:
                assert control.verify_start(SHA) == 0
            assert "POSTCHECK=VERIFIED_PAPER_READY" in receipt.getvalue()
            assert "INSTALLED_SHA=" + SHA in receipt.getvalue()
            assert readiness.call_args.kwargs["target"] == SHA
            assert readiness.call_args.kwargs["require_gitless_telegram"] is True
            readiness.return_value = "BLOCKED: protection"
            with redirect_stdout(StringIO()) as receipt:
                assert control.verify_start(SHA) == 2
            assert "POSTCHECK=BLOCKED_PAPER_READINESS" in receipt.getvalue()
            readiness.reset_mock()
            identity.return_value = "c" * 40
            assert control.verify_start(SHA) == 2
            readiness.assert_not_called()


if __name__ == "__main__":
    unittest.main()


def test_readonly_refusal_recovery_is_one_pinned_detached_owner_request(monkeypatch):
    from pathlib import Path
    stage = Path("/var/lib/bybitscanner-stage-git-" + SHA)
    monkeypatch.setattr(control, "_verified_take_closed_stage", lambda sha: stage)
    action = "update-after-readonly-stop-refusal"
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return completed(cmd, out="LoadState=not-found\n" if cmd[0] == "systemctl" else "")

    assert control.submit(action, SHA, R, "win-pc", run=run, uid=0) == 0
    assert len(calls) == 2
    assert calls[1][0] == "systemd-run"
    assert "--working-directory=" + str(stage) in calls[1]
    assert calls[1][-5:] == ["-m", "tools.paper_maintenance", SHA, "--action", action]
    assert "--description=BybitScanner " + action + " " + SHA + " origin=win-pc" in calls[1]


def test_readonly_refusal_recovery_requires_exact_paper_postcheck(monkeypatch):
    action = "update-after-readonly-stop-refusal"
    output = ("LoadState=loaded\nActiveState=active\nSubState=exited\n"
              "Result=success\nExecMainStatus=0\nDescription=BybitScanner "
              + action + " " + SHA + " origin=win-pc\n")
    checked = []
    monkeypatch.setattr(control, "verify_start", lambda target: (checked.append(target), 0)[1])
    run = lambda cmd, **kw: completed(cmd, out=output)
    assert control.status(R, run=run, verify_start_sha="c" * 40) == 2
    assert checked == []
    assert control.status(R, run=run, verify_start_sha=SHA) == 0
    assert checked == [SHA]


def test_take_closed_update_is_one_detached_pinned_stage_owner_request(monkeypatch):
    from pathlib import Path
    target_stage = Path("/var/lib/bybitscanner-stage-git-" + SHA)
    monkeypatch.setattr(control, "_verified_take_closed_stage", lambda sha: target_stage)
    calls = []
    def run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[0] == "systemctl":
            return completed(cmd, out="LoadState=not-found\n")
        return completed(cmd, out="Running as unit")
    assert control.submit("update-take-closed", SHA, R, "win-PC", run=run, uid=0) == 0
    assert len(calls) == 2
    unit = calls[1]
    assert unit[0] == "systemd-run"
    assert "--remain-after-exit" in unit
    assert "--working-directory=" + str(target_stage) in unit
    assert unit[-5:] == ["-m", "tools.paper_maintenance", SHA,
                         "--action", "update-take-closed"]
    assert all("PAPER_AUTO" not in str(s) for s in unit)


def test_take_closed_update_refuses_unverified_old_installed_source(monkeypatch):
    from pathlib import Path
    import pytest
    monkeypatch.setattr(control, "__file__", "/opt/BybitScanner/tools/vps_owner_control.py")
    calls = []
    def read_only_probe(cmd, **kwargs):
        calls.append(cmd)
        assert cmd[0] == "systemctl"  # UUID status is safe even on old source.
        return completed(cmd, out="LoadState=not-found\nDescription=\n")
    with pytest.raises(ValueError, match="verified_target_stage"):
        control.submit("update-take-closed", SHA, R, "win-PC",
                       run=read_only_probe, uid=0)
    assert len(calls) == 1  # Never submit a new stage from an old checkout.


def test_finished_take_closed_update_requires_same_exact_postcheck():
    from unittest.mock import patch
    output = ("LoadState=loaded\nActiveState=active\nSubState=exited\n"
              "Result=success\nExecMainStatus=0\n"
              "Description=BybitScanner update-take-closed " + SHA[:12]
              + " origin=win-PC\n")
    run = lambda cmd, **kw: completed(cmd, out=output)
    with patch.object(control, "verify_update", return_value=2) as checker:
        assert control.status(R, run=run, verify_sha=SHA) == 2
        checker.assert_called_once_with(SHA)



def test_owner_github_status_enable_is_one_pinned_detached_request(monkeypatch):
    from tools import vps_release_identity as identity
    monkeypatch.setattr(identity, "verify_release", lambda root: SHA)
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return completed(cmd, out="LoadState=not-found\n" if cmd[0] == "systemctl" else "")
    assert control.submit("github-status-enable", "installed", R,
                          "win-laptop", run=run, uid=0) == 0
    assert len(calls) == 2
    assert calls[1][0] == "systemd-run"
    assert calls[1][-3:] == [SHA, "--action", "github-status-enable"]
    assert "--description=BybitScanner github-status-enable " + SHA + " origin=win-laptop" in calls[1]


def test_diagnostic_owner_outcome_exact_identity_and_canonical_postcheck(monkeypatch):
    calls, proofs = [], []
    active, sub, result, code = "active", "exited", "success", "0"
    description = f"BybitScanner update {SHA} origin=PRIVATE-DESKTOP"

    def run(cmd, **kwargs):
        calls.append(cmd)
        assert cmd[:2] == ["systemctl", "show"]
        assert cmd[-1] == control.unit_name(R)
        return completed(cmd, out=(
            f"LoadState=loaded\nActiveState={active}\nSubState={sub}\n"
            f"Result={result}\nExecMainStatus={code}\nDescription={description}\n"))

    def proof(target):
        proofs.append(target)
        print("POSTCHECK=VERIFIED_EDITOR_ONLY")
        print("PRIVATE_DATABASE_IDENTITY")
        return 0

    monkeypatch.setattr(control, "verify_update", proof)
    read = lambda: control.read_diagnostic_outcome(R, "update", SHA, run=run)
    value = read()
    assert value == dict(owner_request_id=R, owner_action="update", target_sha=SHA,
                         state="FINISHED_OK", result="success", exit_code=0,
                         postcheck="VERIFIED_EDITOR_ONLY")
    assert proofs == [SHA] and len(calls) == 1
    for wrong in (f"BybitScanner update {SHA[:12]} origin=win-pc",
                  f"BybitScanner stop {SHA} origin=win-pc",
                  f"BybitScanner update {'c'*40} origin=win-pc"):
        description = wrong
        assert read()["state"] == "UNPROVEN"
    description = f"BybitScanner update {SHA} origin=win-pc"
    active, sub, result, code = "failed", "failed", "exit-code", "2"
    value = read()
    assert (value["state"], value["exit_code"], value["postcheck"]) == ("FAILED", 2, "NOT_RUN")
    active, sub, result, code = "activating", "start", "success", "0"
    assert read()["state"] == "RUNNING"
    assert read()["exit_code"] is None
    assert proofs == [SHA]
    active, sub, result, code = "active", "exited", "success", "0"
    monkeypatch.setattr(control, "verify_update", lambda _: 0)
    assert read()["postcheck"] == "BLOCKED"
    assert all(cmd[0] == "systemctl" and cmd[1] == "show" for cmd in calls)


def test_signed_start_owner_outcome_checks_current_readiness_without_mutations(monkeypatch):
    for action in ("start", "update-and-start"):
        fields = dict(active="active", sub="exited", result="success", code="0",
                      description=f"BybitScanner {action} {SHA} origin=private-origin")
        calls, proofs = [], []

        def run(cmd, **kwargs):
            calls.append(cmd)
            assert cmd[:2] == ["systemctl", "show"]
            assert cmd[-1] == control.unit_name(R)
            return completed(cmd, out=(
                f"LoadState=loaded\nActiveState={fields['active']}\n"
                f"SubState={fields['sub']}\nResult={fields['result']}\n"
                f"ExecMainStatus={fields['code']}\nDescription={fields['description']}\n"))

        def proof(target):
            proofs.append(target)
            print("POSTCHECK=VERIFIED_PAPER_READY")
            print("PRIVATE_RUNTIME_DETAIL")
            return 0

        monkeypatch.setattr(control, "verify_start", proof)
        monkeypatch.setattr(control, "verify_update",
                            lambda *_: (_ for _ in ()).throw(AssertionError("wrong postcheck")))
        read = lambda: control.read_diagnostic_outcome(R, action, SHA, run=run)
        assert read() == dict(owner_request_id=R, owner_action=action, target_sha=SHA,
                              state="FINISHED_OK", result="success", exit_code=0,
                              postcheck="VERIFIED_PAPER_READY")
        assert proofs == [SHA]
        fields["description"] = f"BybitScanner {action} {'c' * 40} origin=private-origin"
        assert read()["state"] == "UNPROVEN"
        fields["description"] = f"BybitScanner {action} {SHA} origin=private-origin"
        fields.update(active="activating", sub="start")
        assert read()["postcheck"] == "NOT_RUN"
        fields.update(active="failed", sub="failed", result="exit-code", code="2")
        assert read()["postcheck"] == "NOT_RUN"
        assert proofs == [SHA]
        fields.update(active="active", sub="exited", result="success", code="0")
        monkeypatch.setattr(control, "verify_start", lambda _: 0)
        assert read()["postcheck"] == "BLOCKED"
        monkeypatch.setattr(control, "verify_start", lambda _: 2)
        assert read()["postcheck"] == "BLOCKED"
        assert len(calls) == 6
