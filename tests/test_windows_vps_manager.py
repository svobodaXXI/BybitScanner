"""Safety regression tests for standalone Windows VPS Manager commands."""
from __future__ import annotations

import io
import queue
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.windows_vps_manager import (ACTIONS, VPSManager, control_ssh_command,
                                       preferred_route, parse_args, ssh_command,
                                       remember_request_id, recover_last_request_id, run_cli,
                                       gui_owner_status)


class TestWindowsVpsManager(unittest.TestCase):
    def test_all_actions_use_strict_ssh_and_no_interactive_passwords(self) -> None:
        for action in ACTIONS:
            with self.subTest(action=action):
                command = ssh_command("vps.example.org", "bybitscanner", action)
                self.assertEqual(command[0], "ssh")
                self.assertIn("StrictHostKeyChecking=yes", command)
                self.assertIn("BatchMode=yes", command)
                self.assertEqual(command[-2], "bybitscanner@vps.example.org")
                self.assertEqual(command[-1], ACTIONS[action])

    def test_no_write_actions_or_arbitrary_shell(self) -> None:
        for action, remote in ACTIONS.items():
            with self.subTest(action=action):
                self.assertNotIn("systemctl stop", remote)
                self.assertNotIn("systemctl start", remote)
                self.assertNotIn("git pull", remote)
                self.assertNotIn("git reset", remote)
                self.assertNotIn("rm -", remote)
        with self.assertRaises(ValueError):
            ssh_command("vps.example.org", "bybitscanner", "rm -rf /")

    def test_status_action_fails_on_first_unavailable_service(self) -> None:
        # Even if the last service exists, a failure from an earlier
        # systemctl call must propagate to SSH and the GUI status indicator.
        command = ssh_command("vps.example.org", "bybitscanner", "Состояние")
        remote = command[-1]
        self.assertTrue(remote.startswith("set -e; "), remote)
        self.assertEqual(remote, ACTIONS["Состояние"])
        self.assertEqual(remote.count("systemctl show "), 3)
        self.assertNotIn("systemctl start", remote)
        self.assertNotIn("systemctl stop", remote)

    def test_paper_diagnostics_and_update_preflight_fail_on_early_errors(self) -> None:
        # A failed Git inspection or systemctl query must not be masked by
        # a later successful health response in the same SSH command.
        for action in ("Диагностика PAPER", "Предпроверка обновления"):
            with self.subTest(action=action):
                remote = ssh_command("vps.example.org", "bybitscanner", action)[-1]
                self.assertTrue(remote.startswith("set -e; "), remote)
                self.assertEqual(remote, ACTIONS[action])
                self.assertNotIn("systemctl start", remote)
                self.assertNotIn("systemctl stop", remote)

    def test_failed_ssh_and_timeout_are_not_reported_as_success(self) -> None:
        for result, expected in (
            (subprocess.CompletedProcess(["ssh"], 0, stdout="healthy", stderr=""), "success"),
            (subprocess.CompletedProcess(["ssh"], 255, stdout="", stderr="denied"), "failure"),
        ):
            with self.subTest(exit_code=result.returncode):
                state = SimpleNamespace(events=queue.Queue())
                with patch("tools.windows_vps_manager.subprocess.run", return_value=result):
                    VPSManager.worker(state, ["ssh", "example"])
                kind, output = state.events.get_nowait()
                self.assertEqual(kind, expected)
                self.assertIn(f"Exit code: {result.returncode}", output)

        state = SimpleNamespace(events=queue.Queue())
        with patch("tools.windows_vps_manager.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("ssh", 45)):
            VPSManager.worker(state, ["ssh", "example"])
        kind, output = state.events.get_nowait()
        self.assertEqual(kind, "failure")
        self.assertIn("TimeoutExpired", output)

    def test_status_bar_distinguishes_failures_from_success(self) -> None:
        for kind, expected in (("failure", "Ошибка"), ("success", "Успешно"),
                               ("failed", "Операция завершилась ошибкой"),
                               ("unproven", "Результат не доказан")):
            with self.subTest(kind=kind):
                status = Mock()
                button = Mock()
                fake = SimpleNamespace(
                    events=queue.Queue(), write=Mock(), status=status,
                    buttons=[button], after=Mock(), drain=Mock(), busy=True,
                )
                fake.events.put((kind, "diagnostic output"))
                VPSManager.drain(fake)
                self.assertFalse(fake.busy)
                self.assertTrue(status.set.call_args.args[0].startswith(expected))
                button.state.assert_called_with(["!disabled"])
                fake.write.assert_called_once_with("diagnostic output")

    def test_git_actions_are_safe_directory_scoped(self) -> None:
        for action, remote in ACTIONS.items():
            if "git " in remote:
                with self.subTest(action=action):
                    self.assertNotIn("git -C", remote)
                    self.assertIn("git -c safe.directory=/opt/BybitScanner -C /opt/BybitScanner", remote)
                    self.assertNotIn("config --global", remote)

    def test_gitless_installed_release_is_observable_without_false_clean_claim(self) -> None:
        for name in ("Git / локальные изменения", "Предпроверка обновления"):
            with self.subTest(name=name):
                remote = ACTIONS[name]
                self.assertTrue(remote.startswith("set -e; "))
                self.assertIn("test -e /opt/BybitScanner/.git", remote)
                self.assertIn("GIT_WORKTREE=ABSENT", remote)
                self.assertIn("GIT_STATUS=UNKNOWN", remote)
                self.assertIn("/api/health", remote)
                self.assertNotIn("git pull", remote)
                self.assertNotIn("git reset", remote)
        self.assertIn("DEPLOY_PREFLIGHT=NOT_PROVEN", ACTIONS["Предпроверка обновления"])

    def test_explicit_key_is_offered_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "bybitscanner_laptop"
            key.write_text("", encoding="utf-8")
            command = ssh_command("vps.example.org", "bybitscanner", "Состояние", str(key))
            self.assertEqual(command[command.index("-i") + 1], str(key))
            self.assertIn("IdentitiesOnly=yes", command)
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertEqual(command[-2], "bybitscanner@vps.example.org")
            self.assertEqual(command[-1], ACTIONS["Состояние"])

    def test_without_key_command_is_unchanged(self) -> None:
        self.assertEqual(
            ssh_command("vps.example.org", "bybitscanner", "Состояние"),
            ssh_command("vps.example.org", "bybitscanner", "Состояние", "   "),
        )
        self.assertNotIn("-i", ssh_command("vps.example.org", "bybitscanner", "Состояние"))

    def test_missing_key_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                ssh_command(
                    "vps.example.org", "bybitscanner", "Состояние",
                    str(Path(folder) / "absent_key"),
                )

    def test_shortcut_arguments_prefill_fields(self) -> None:
        args = parse_args(["--host", "vps.example.org", "--user", "vpsmanager", "--key", "C:/k"])
        self.assertEqual((args.host, args.user, args.key), ("vps.example.org", "vpsmanager", "C:/k"))
        defaults = parse_args([])
        self.assertEqual((defaults.host, defaults.user, defaults.key), ("", "bybitscanner", None))
        # Unknown switches must not crash a windowed executable.
        self.assertEqual(parse_args(["--bogus", "x"]).host, "")

    def test_invalid_remote_targets_rejected(self) -> None:
        for hostname, user in [
            ("-oProxyCommand=evil", "bybitscanner"),
            ("hostname;id", "bybitscanner"),
            ("host with spaces", "bybitscanner"),
            ("host", "root;id"),
            ("", "bybitscanner"),
            ("host", "-root"),
        ]:
            with self.subTest(hostname=hostname, user=user):
                with self.assertRaises(ValueError):
                    ssh_command(hostname, user, "Состояние")


    def test_owner_controls_share_validated_ssh_route_with_read_only_manager(self):
        request = "1" * 32
        cmd = control_ssh_command("bybitscanner-vps", "", "", "update",
                                  sha="a" * 40, request_id=request,
                                  origin="win-OWNER-PC")
        self.assertEqual(cmd[-2], "bybitscanner-vps")
        self.assertIn("BatchMode=yes", cmd)
        self.assertIn("StrictHostKeyChecking=yes", cmd)
        self.assertIn("tools.vps_owner_control submit update", cmd[-1])
        self.assertIn("--request-id " + request, cmd[-1])
        self.assertIn("win-OWNER-PC", cmd[-1])
        start = control_ssh_command("bybitscanner-vps", "", "", "start",
                                    sha="installed", request_id=request)
        self.assertIn("submit start installed", start[-1])
        self.assertIn("tools.vps_owner_control status " + request,
                      control_ssh_command("bybitscanner-vps", "", "", "status",
                                          request_id=request)[-1])

    def test_owner_control_blocks_injection_and_unapproved_target(self):
        for name, args in (
            ("missing_sha", dict(operation="update", sha="", request_id="1"*32)),
            ("bad_sha", dict(operation="update", sha="x"*40, request_id="1"*32)),
            ("bad_request", dict(operation="stop", sha="installed", request_id="bad")),
            ("bad_mode", dict(operation="reset", sha="a"*40, request_id="1"*32)),
            ("bad_origin", dict(operation="start", sha="installed", request_id="1"*32,
                                origin="win; echo bad")),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    control_ssh_command("bybitscanner-vps", "", "", **args)

    def test_gui_unknown_submit_checks_status_without_resubmitting(self):
        fake = SimpleNamespace(events=queue.Queue(), host=Mock(), user=Mock(), key=Mock())
        fake.host.get.return_value = "bybitscanner-vps"
        fake.user.get.return_value = ""
        fake.key.get.return_value = ""
        request = "1" * 32
        submit = subprocess.CompletedProcess(["ssh"], 255, stdout="", stderr="lost")
        status = subprocess.CompletedProcess(["ssh"], 3, stdout=(
            "REQUEST_ID=" + request + "\nSTATUS=RUNNING\n"), stderr="")
        with patch("tools.windows_vps_manager.subprocess.run", side_effect=[submit, status]) as run:
            VPSManager.worker_control(fake, ["ssh", "submit"], "update", request)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(fake.events.get_nowait()[0], "submitted")

    def test_gui_status_never_claims_success_without_matching_request(self):
        request = "1" * 32
        for code, response, expected in (
            (0, "REQUEST_ID=" + request + "\nSTATUS=FINISHED_OK\n", "success"),
            (3, "REQUEST_ID=" + request + "\nSTATUS=RUNNING\n", "submitted"),
            (2, "REQUEST_ID=" + request + "\nSTATUS=FAILED\n", "failed"),
            (0, "", "unproven"),
            (0, "REQUEST_ID=" + "2" * 32 + "\nSTATUS=FINISHED_OK\n", "unproven"),
            (255, "REQUEST_ID=" + request + "\nSTATUS=FINISHED_OK\n", "unproven"),
            (0, "REQUEST_ID=" + request +
             "\nSTATUS=FINISHED_OK\nSTATUS=FAILED\n", "unproven"),
        ):
            with self.subTest(code=code, expected=expected):
                fake = SimpleNamespace(events=queue.Queue())
                response_obj = subprocess.CompletedProcess(
                    ["ssh"], code, stdout=response, stderr="")
                with patch("tools.windows_vps_manager.subprocess.run",
                           return_value=response_obj):
                    VPSManager.worker_control(fake, ["ssh", "status"], "status", request)
                self.assertEqual(fake.events.get_nowait()[0], expected)

    def test_gui_submit_unknown_response_is_not_success_or_resubmitted(self):
        request = "1" * 32
        fake = SimpleNamespace(events=queue.Queue(), host=Mock(), user=Mock(), key=Mock())
        fake.host.get.return_value = "bybitscanner-vps"
        fake.user.get.return_value = ""
        fake.key.get.return_value = ""
        for submit_code, submit_output, expected in (
            (255, "", "unproven"),
            (0, "REQUEST_ID=" + request + "\nSUBMISSION=ACCEPTED\n", "submitted"),
        ):
            with self.subTest(expected=expected):
                replies = [
                    subprocess.CompletedProcess(["ssh"], submit_code,
                                                stdout=submit_output, stderr="")
                ] + [
                    subprocess.CompletedProcess(["ssh"], 0,
                                                stdout="REQUEST_ID=" + "2" * 32 +
                                                "\nSTATUS=FINISHED_OK\n", stderr="")
                    for _ in range(3)
                ]
                with (patch("tools.windows_vps_manager.subprocess.run",
                            side_effect=replies) as remote,
                      patch("tools.windows_vps_manager.time.sleep")):
                    VPSManager.worker_control(fake, ["ssh", "submit"], "stop", request)
                self.assertEqual(fake.events.get_nowait()[0], expected)
                self.assertEqual(remote.call_count, 4)
                self.assertTrue(all(
                    "tools.vps_owner_control status " + request in call.args[0][-1]
                    for call in remote.call_args_list[1:]
                ))

    def test_request_id_persisted_and_validated_without_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "VPSManager" / "last_request_id"
            request = "f" * 32
            remember_request_id(request, path)
            self.assertEqual(recover_last_request_id(path), request)
            self.assertEqual(path.read_text(encoding="ascii"), request + "\n")
            path.write_text("invalid or malicious ID", encoding="ascii")
            self.assertEqual(recover_last_request_id(path), "")
            with self.assertRaises(ValueError):
                remember_request_id("invalid", path)

    def test_cli_unknown_ssh_reply_recovers_status_without_resubmission(self):
        with tempfile.TemporaryDirectory() as folder:
            cached = Path(folder) / "last_request_id"
            request = "f" * 32
            with (patch("tools.windows_vps_manager.request_id_store", return_value=cached),
                  patch("tools.windows_vps_manager.preferred_route",
                        return_value=("bybitscanner-vps", "")),
                  patch("tools.windows_vps_manager.subprocess.run",
                        side_effect=[
                            subprocess.TimeoutExpired("ssh", 35),
                            subprocess.CompletedProcess(["ssh"], 0,
                                                        stdout="REQUEST_ID=" + request
                                                        + "\nSTATUS=FINISHED_OK\n", stderr=""),
                        ]) as remote,
                  patch("sys.stdout", new_callable=io.StringIO) as stdout):
                self.assertEqual(run_cli(parse_args([
                    "--operation", "stop", "--request-id", request])), 2)
                self.assertEqual(recover_last_request_id(cached), request)
                self.assertIn("REQUEST_ID=" + request, stdout.getvalue())
                self.assertEqual(run_cli(parse_args(["--operation", "status"])), 0)
                self.assertEqual(remote.call_count, 2)
                self.assertIn("tools.vps_owner_control submit stop installed",
                              remote.call_args_list[0].args[0][-1])
                self.assertIn("tools.vps_owner_control status " + request,
                              remote.call_args_list[1].args[0][-1])
                self.assertNotIn(" submit ", remote.call_args_list[1].args[0][-1])

    def test_cli_status_distinguishes_known_states_from_unknown_ssh(self):
        request = "e" * 32
        for code, response, expected, exit_code in (
            (0, "REQUEST_ID=" + request + "\nSTATUS=FINISHED_OK\n",
             "OPERATION_FINISHED_OK", 0),
            (3, "REQUEST_ID=" + request + "\nSTATUS=RUNNING\n",
             "OPERATION_RUNNING", 3),
            (2, "REQUEST_ID=" + request + "\nSTATUS=FAILED\n",
             "OPERATION_FAILED", 2),
            (2, "STATUS=UNPROVEN REQUEST_ID=" + request + "\n",
             "REMOTE_STATUS_UNPROVEN", 2),
            (255, "REQUEST_ID=" + request + "\nSTATUS=RUNNING\n",
             "REMOTE_STATUS_UNPROVEN", 2),
            (3, "REQUEST_ID=" + "a" * 32 + "\nSTATUS=RUNNING\n",
             "REMOTE_STATUS_UNPROVEN", 2),
        ):
            with self.subTest(code=code, expected=expected):
                reply = subprocess.CompletedProcess(
                    ["ssh"], code, stdout=response, stderr="")
                with (patch("tools.windows_vps_manager.preferred_route",
                            return_value=("bybitscanner-vps", "")),
                      patch("tools.windows_vps_manager.subprocess.run",
                            return_value=reply) as remote,
                      patch("sys.stdout", new_callable=io.StringIO) as output):
                    result = run_cli(parse_args([
                        "--operation", "status", "--request-id", request]))
                self.assertEqual(result, exit_code)
                self.assertIn(expected + "; request_id=" + request,
                              output.getvalue())
                self.assertEqual(remote.call_count, 1)
                self.assertIn("tools.vps_owner_control status " + request,
                              remote.call_args.args[0][-1])

    def test_existing_alias_detected_without_rewriting_ssh_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / ".ssh"
            config.mkdir()
            (config / "config").write_text(
                "Host bybitscanner-vps\n    HostName 212.193.14.116\n"
                "    User root\n", encoding="utf-8")
            with patch("tools.windows_vps_manager.Path.home", return_value=Path(temp)):
                self.assertEqual(preferred_route(), ("bybitscanner-vps", ""))


if __name__ == "__main__":
    unittest.main()
