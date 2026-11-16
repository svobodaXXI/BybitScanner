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
                                       known_windows_device, preferred_key, PREFLIGHT,
                                       watch_owner_request)


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
            (subprocess.CompletedProcess(["ssh"], 0, stdout="healthy", stderr=""), "observed"),
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
                    events=queue.Queue(), write_result=Mock(), status=status,
                    buttons=[button], after=Mock(), drain=Mock(), busy=True,
                )
                fake.events.put((kind, "diagnostic output"))
                VPSManager.drain(fake)
                self.assertFalse(fake.busy)
                self.assertTrue(status.set.call_args.args[0].startswith(expected))
                button.state.assert_called_with(["!disabled"])
                fake.write_result.assert_called_once_with("diagnostic output")

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

    def test_every_owner_command_enters_repository_before_module_import(self):
        request = "1" * 32
        for mode, sha in (
            ("update", "a" * 40),
            ("start", "installed"),
            ("stop", "installed"),
            ("update-and-start", "a" * 40),
            ("status", ""),
            ("list", ""),
        ):
            with self.subTest(mode=mode):
                command = control_ssh_command(
                    "bybitscanner-vps", "", "", mode, sha=sha,
                    request_id=request if mode != "list" else "",
                )
                self.assertEqual(command[-2], "bybitscanner-vps")
                self.assertTrue(
                    command[-1].startswith(
                        "cd /opt/BybitScanner && "
                        "/opt/BybitScanner/venv/bin/python -m tools.vps_owner_control "
                    ),
                    command[-1],
                )

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

    def test_completed_journal_entries_have_independent_copy_targets(self):
        fake = SimpleNamespace(log=Mock(), _copy_seq=0, copy_result=Mock())
        first = "PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED\\nfirst"
        second = "REQUEST_ID=abc\\nSTATUS=FINISHED_OK\\nsecond"
        VPSManager.write_result(fake, first)
        VPSManager.write_result(fake, second)
        self.assertEqual(fake._copy_seq, 2)
        self.assertEqual(fake.log.tag_bind.call_count, 2)
        self.assertEqual(fake.log.insert.call_args_list[0].args[1], first + "\n")
        self.assertEqual(fake.log.insert.call_args_list[1].args[1],
                         "📋 Скопировать результат")
        self.assertEqual(fake.log.insert.call_args_list[2].args[1], "\n\n")
        self.assertEqual(fake.log.insert.call_args_list[3].args[1], second + "\n")
        self.assertEqual(fake.log.insert.call_args_list[4].args[1],
                         "📋 Скопировать результат")
        self.assertEqual(fake.log.insert.call_args_list[5].args[1], "\n\n")
        self.assertNotEqual(
            fake.log.tag_bind.call_args_list[0].args[0],
            fake.log.tag_bind.call_args_list[1].args[0],
        )
        fake.log.tag_bind.call_args_list[0].args[2](None)
        fake.log.tag_bind.call_args_list[1].args[2](None)
        self.assertEqual([c.args for c in fake.copy_result.call_args_list],
                         [(first, "copy_result_1"), (second, "copy_result_2")])
        self.assertEqual(fake.log.see.call_count, 2)

    def test_copy_result_uses_only_one_result_and_no_remote_call(self):
        fake = SimpleNamespace(
            clipboard_clear=Mock(), clipboard_append=Mock(),
            update_idletasks=Mock())
        output = "Preflight\\nline 1\\nline 2\\nfull output"
        VPSManager.copy_result(fake, output)
        fake.clipboard_clear.assert_called_once_with()
        fake.clipboard_append.assert_called_once_with(output)
        fake.update_idletasks.assert_called_once_with()

    def test_successful_copy_shows_green_confirmation_for_only_that_entry(self):
        log = Mock()
        log.index.return_value = "7.0"
        fake = SimpleNamespace(
            clipboard_clear=Mock(), clipboard_append=Mock(),
            update_idletasks=Mock(), log=log)
        output = "Preflight\nwhole result"
        VPSManager.copy_result(fake, output, "copy_result_2")
        fake.clipboard_append.assert_called_once_with(output)
        log.replace.assert_called_once_with(
            "7.0", "copy_result_2.last", "✓ Скопировано", "copy_result_2")
        log.tag_configure.assert_called_once_with(
            "copy_result_2", foreground="#17803d", underline=False)
        self.assertEqual(log.configure.call_args_list[0].kwargs["state"], "normal")
        self.assertEqual(log.configure.call_args_list[-1].kwargs["state"], "disabled")

    def test_failed_clipboard_copy_does_not_show_success(self):
        from tkinter import TclError
        fake = SimpleNamespace(
            clipboard_clear=Mock(),
            clipboard_append=Mock(side_effect=TclError("clipboard unavailable")),
            update_idletasks=Mock(), log=Mock())
        with patch("tools.windows_vps_manager.messagebox.showerror") as error:
            VPSManager.copy_result(fake, "result", "copy_result_1")
        error.assert_called_once()
        fake.log.replace.assert_not_called()
        fake.log.tag_configure.assert_not_called()

    def test_list_readonly_empty_is_not_monolith_success(self):
        cmd = ["ssh", "list-only"]
        cases = (
            (0, "", "", "observed", "REQUEST_LIST=EMPTY"),
            (0, "bybitscanner-owner-abc.service loaded active exited", "",
             "observed", "bybitscanner-owner-abc"),
            (255, "", "banner exchange timeout SECRET", "unproven",
             "LIST_FAILURE_CLASS=SSH_BANNER_FAILURE"),
            (2, "REQUEST_LIST=UNPROVEN", "secret message", "unproven",
             "LIST_FAILURE_CLASS=REMOTE_COMMAND_FAILED"),
        )
        for exit_code, stdout, stderr, expected_kind, expected_text in cases:
            with self.subTest(code=exit_code, stdout=stdout):
                fake = SimpleNamespace(events=queue.Queue())
                reply = subprocess.CompletedProcess(cmd, exit_code, stdout, stderr)
                with patch("tools.windows_vps_manager.subprocess.run",
                           return_value=reply) as remote:
                    VPSManager.worker_control(fake, cmd, "list", "")
                remote.assert_called_once()
                kind, output = fake.events.get_nowait()
                self.assertEqual(kind, expected_kind)
                self.assertIn(expected_text, output)
                self.assertNotIn("SECRET", output)
                self.assertNotIn("secret message", output)

    def test_list_transport_timeout_remains_unknown_without_retry(self):
        cmd = ["ssh", "list-only"]
        fake = SimpleNamespace(events=queue.Queue())
        with patch("tools.windows_vps_manager.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("ssh", 35)) as remote:
            VPSManager.worker_control(fake, cmd, "list", "")
        remote.assert_called_once()
        kind, output = fake.events.get_nowait()
        self.assertEqual(kind, "unproven")
        self.assertIn("LIST_FAILURE_CLASS=SSH_CLIENT_TIMEOUT", output)
        self.assertNotIn("повторять операцию нельзя", output)

    def test_status_gui_uses_explicit_exact_id_across_devices_read_only(self):
        request = "a" * 32
        fake = SimpleNamespace(
            busy=False, sha=Mock(), request_id=Mock(), last_request_id="b" * 32,
            host=Mock(), user=Mock(), key=Mock(), origin="win-pc-test",
            status=Mock(), buttons=[Mock()], write=Mock(),
        )
        fake.sha.get.return_value = ""
        fake.request_id.get.return_value = request
        fake.host.get.return_value = "bybitscanner-vps"
        fake.user.get.return_value = ""
        fake.key.get.return_value = ""
        with (patch("tools.windows_vps_manager.control_ssh_command",
                    return_value=["ssh", "status-only"]) as cmd,
              patch("tools.windows_vps_manager.threading.Thread") as worker):
            VPSManager.run_control(fake, "status")
        cmd.assert_called_once()
        self.assertEqual(cmd.call_args.args[3], "status")
        self.assertEqual(cmd.call_args.kwargs["request_id"], request)
        self.assertNotEqual(cmd.call_args.kwargs["request_id"],
                            fake.last_request_id)
        worker.assert_called_once()
        self.assertEqual(worker.call_args.kwargs["args"][1:], ("status", request))
        fake.buttons[0].state.assert_called_once_with(["disabled"])

    def test_gui_automatically_watches_same_uuid_until_terminal_success(self):
        req = "9" * 32
        command = ["ssh", "exact-status"]
        sequence = iter([
            subprocess.CompletedProcess(command, 3, stdout=f"REQUEST_ID={req}\nSTATUS=RUNNING\n", stderr=""),
            subprocess.CompletedProcess(command, 3, stdout=f"REQUEST_ID={req}\nSTATUS=RUNNING\n", stderr=""),
            subprocess.CompletedProcess(command, 0, stdout=f"REQUEST_ID={req}\nSTATUS=FINISHED_OK\n", stderr=""),
        ])
        sleep = Mock()
        run = Mock(side_effect=lambda *_a, **_kw: next(sequence))
        state, details = watch_owner_request(
            command, req, initially_submitted=True, run=run, sleep=sleep)
        self.assertEqual(state, "success")
        self.assertIn("STATUS=FINISHED_OK", details)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all(call.args[0] == command for call in run.call_args_list))

    def test_gui_watcher_unknown_connection_never_replays_owner_action(self):
        req = "a" * 32
        command = ["ssh", "status-only"]
        run = Mock(side_effect=subprocess.TimeoutExpired("ssh", 20))
        state, details = watch_owner_request(
            command, req, initially_submitted=True, run=run,
            sleep=lambda *_: None)
        self.assertEqual(state, "submitted")  # known accepted, terminal result unknown
        self.assertIn("STATUS_UNPROVEN", details)
        self.assertEqual(run.call_count, 3)
        self.assertTrue(all(call.args[0] == command for call in run.call_args_list))

    def test_gui_watcher_unknown_submission_not_upgraded_to_success(self):
        req = "b" * 32
        command = ["ssh", "status-only"]
        reply = subprocess.CompletedProcess(
            command, 0, stdout="REQUEST_ID=" + "c" * 32 + "\nSTATUS=FINISHED_OK\n",
            stderr="")
        run = Mock(return_value=reply)
        state, details = watch_owner_request(
            command, req, initially_submitted=False, run=run,
            sleep=lambda *_: None)
        self.assertEqual(state, "unproven")
        self.assertIn("STATUS_UNPROVEN", details)
        self.assertEqual(run.call_count, 3)

    def test_gui_unknown_submit_checks_status_without_resubmitting(self):
        fake = SimpleNamespace(events=queue.Queue(), host=Mock(), user=Mock(), key=Mock())
        fake.host.get.return_value = "bybitscanner-vps"
        fake.user.get.return_value = ""
        fake.key.get.return_value = ""
        request = "1" * 32
        submit = subprocess.CompletedProcess(["ssh"], 255, stdout="", stderr="lost")
        status = subprocess.CompletedProcess(["ssh"], 0, stdout=(
            "REQUEST_ID=" + request + "\nSTATUS=FINISHED_OK\n"), stderr="")
        with patch("tools.windows_vps_manager.subprocess.run", side_effect=[submit, status]) as run:
            VPSManager.worker_control(fake, ["ssh", "submit"], "update", request)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(fake.events.get_nowait()[0], "success")

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


    def test_known_windows_device_uses_only_exact_confirmed_profiles(self):
        self.assertEqual(known_windows_device(r"C:\Users\svobo"), "pc")
        self.assertEqual(known_windows_device(r"c:/users/SVOBODA21/"), "laptop")
        self.assertEqual(known_windows_device(r"C:\Users\unexpected"), "")
        self.assertEqual(known_windows_device(r"D:\Users\svobo"), "")
        self.assertEqual(known_windows_device(""), "")

    def test_laptop_autoroutes_without_pc_alias_and_pins_its_own_key(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            key = root / ".ssh" / "bybitscanner_laptop"
            key.parent.mkdir()
            key.write_text("test placeholder", encoding="ascii")
            (root / ".ssh" / "config").write_text(
                "Host bybitscanner-vps\n  HostName 212.193.14.116\n", encoding="ascii")
            with (patch.dict("tools.windows_vps_manager.os.environ",
                             {"USERPROFILE": r"C:\Users\SVOBODA21"}),
                  patch("tools.windows_vps_manager.Path.home", return_value=root)):
                self.assertEqual(preferred_route(), ("83.217.213.181", "root"))
                self.assertEqual(preferred_key("83.217.213.181", "root"), str(key))
                self.assertEqual(preferred_key("212.193.14.116", "root"), "")
                cmd = control_ssh_command(*preferred_route(), str(key), "list")
            self.assertEqual(cmd[:3], ["ssh", "-F", "none"])
            self.assertIn("StrictHostKeyChecking=yes", cmd)
            self.assertEqual(cmd[cmd.index("-i") + 1], str(key))
            self.assertEqual(cmd[-2], "root@83.217.213.181")
            self.assertNotIn(" submit ", cmd[-1])

    def test_pc_autoroutes_alias_without_laptop_identity(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            (root / ".ssh").mkdir()
            (root / ".ssh" / "config").write_text(
                "Host bybitscanner-vps\n  HostName 212.193.14.116\n", encoding="ascii")
            with (patch.dict("tools.windows_vps_manager.os.environ",
                             {"USERPROFILE": r"C:\Users\svobo"}),
                  patch("tools.windows_vps_manager.Path.home", return_value=root)):
                self.assertEqual(preferred_route(), ("bybitscanner-vps", ""))
                self.assertEqual(preferred_key("bybitscanner-vps", ""), "")
            # Direct fallback is used only when the alias is genuinely absent.
            (root / ".ssh" / "config").unlink()
            with (patch.dict("tools.windows_vps_manager.os.environ",
                             {"USERPROFILE": r"C:\Users\svobo"}),
                  patch("tools.windows_vps_manager.Path.home", return_value=root)):
                self.assertEqual(preferred_route(), ("212.193.14.116", "root"))
                self.assertEqual(
                    preferred_key("212.193.14.116", "root"),
                    str(root / ".ssh" / "bybitscanner_vdsina_gateway_20261030"),
                )

    def test_preflight_is_single_read_only_command_not_runtime_acceptance(self):
        cmd = control_ssh_command("bybitscanner-vps", "", "", "preflight")
        self.assertEqual(cmd[-2], "bybitscanner-vps")
        remote = cmd[-1]
        self.assertEqual(remote, PREFLIGHT)
        for required in (
            "tools.vps_release_identity verify", "bybitscanner-paper-backend.service",
            "bybitscanner-telegram.service", "bybitscanner-manual-main-read.service",
            "/api/health", "/api/scanner/status", "/api/robot/autopilot",
            "8766/health", "PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED",
        ):
            self.assertIn(required, remote)
        for forbidden in (
            "systemctl stop", "systemctl start", "submit ", "paper_maintenance --action",
            "sqlite3", "git reset", "curl -X POST", "LIVE",
        ):
            self.assertNotIn(forbidden, remote)
        with patch("tools.windows_vps_manager.subprocess.run",
                   return_value=subprocess.CompletedProcess(
                       cmd, 0, stdout="PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED\\n",
                       stderr="")):
            fake = SimpleNamespace(events=queue.Queue())
            VPSManager.worker_control(fake, cmd, "preflight", "")
        self.assertEqual(fake.events.get_nowait()[0], "observed")
        self.assertIn("preflight", parse_args(["--operation", "preflight"]).operation)

    def test_preflight_ssh_failure_never_reports_success(self):
        cmd = control_ssh_command("bybitscanner-vps", "", "", "preflight")
        with patch("tools.windows_vps_manager.subprocess.run",
                   return_value=subprocess.CompletedProcess(
                       cmd, 255, stdout="", stderr="banner timeout")):
            fake = SimpleNamespace(events=queue.Queue())
            VPSManager.worker_control(fake, cmd, "preflight", "")
        self.assertEqual(fake.events.get_nowait()[0], "unproven")

    def test_cli_preflight_failure_reports_sanitized_cause_and_preserves_fail_closed(self):
        cases = (
            (255, "banner exchange: Connection to 1.2.3.4 port 22: invalid format",
             "SSH_BANNER_FAILURE"),
            (255, "Permission denied (publickey). key-private-secret",
             "SSH_AUTH_REJECTED"),
            (255, "Host key verification failed.", "SSH_HOST_KEY_REJECTED"),
            (1, "bash: /opt/BybitScanner/venv/bin/python: No such file or directory",
             "REMOTE_REQUIRED_FILE_MISSING"),
            (7, "curl: (7) Failed to connect to localhost", "REMOTE_API_UNREACHABLE"),
            (0, "", "REMOTE_RECEIPT_MISSING"),
        )
        for exit_code, stderr, kind in cases:
            with self.subTest(kind=kind):
                completed = subprocess.CompletedProcess(
                    ["ssh"], exit_code, stdout="partial stdout", stderr=stderr)
                with (patch("tools.windows_vps_manager.preferred_route",
                            return_value=("bybitscanner-vps", "")),
                      patch("tools.windows_vps_manager.subprocess.run",
                            return_value=completed) as ssh,
                      patch("sys.stdout", new_callable=io.StringIO) as output):
                    result = run_cli(parse_args(["--operation", "preflight"]))
                self.assertEqual(result, 2)
                self.assertEqual(ssh.call_count, 1)
                self.assertIn("PREFLIGHT_BLOCKED_UNPROVEN", output.getvalue())
                self.assertIn("PREFLIGHT_SSH_EXIT_CODE=" + str(exit_code),
                              output.getvalue())
                self.assertIn("PREFLIGHT_FAILURE_CLASS=" + kind, output.getvalue())
                self.assertNotIn("key-private-secret", output.getvalue())
                self.assertNotIn("1.2.3.4", output.getvalue())

    def test_preflight_timeout_is_classified_without_ssh_retry(self):
        with (patch("tools.windows_vps_manager.preferred_route",
                    return_value=("bybitscanner-vps", "")),
              patch("tools.windows_vps_manager.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("ssh", 35)) as ssh,
              patch("sys.stdout", new_callable=io.StringIO) as output):
            self.assertEqual(run_cli(parse_args(["--operation", "preflight"])), 2)
        self.assertEqual(ssh.call_count, 1)
        self.assertIn("PREFLIGHT_FAILURE_CLASS=SSH_CLIENT_TIMEOUT", output.getvalue())
        self.assertIn("PREFLIGHT_BLOCKED_UNPROVEN", output.getvalue())

    def test_gui_preflight_failure_includes_safe_reason(self):
        cmd = control_ssh_command("bybitscanner-vps", "", "", "preflight")
        with patch("tools.windows_vps_manager.subprocess.run",
                   return_value=subprocess.CompletedProcess(
                       cmd, 255, stdout="", stderr="Permission denied (publickey) secret")):
            fake = SimpleNamespace(events=queue.Queue())
            VPSManager.worker_control(fake, cmd, "preflight", "")
        kind, output = fake.events.get_nowait()
        self.assertEqual(kind, "unproven")
        self.assertIn("PREFLIGHT_FAILURE_CLASS=SSH_AUTH_REJECTED", output)
        self.assertNotIn("secret", output)

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
